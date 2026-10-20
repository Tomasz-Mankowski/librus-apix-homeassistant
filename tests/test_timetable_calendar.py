"""Tests for the timetable calendar (F3): events, titles, descriptions."""

from datetime import date
import json
from typing import Any
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.calendar import LibrusCalendar, TimetableCalendar
from custom_components.librus_apix.const import DOMAIN
from custom_components.librus_apix.schedule import parse_description
from custom_components.librus_apix.timetable import (
    Lesson,
    LessonChange,
    describe,
    lesson_times,
    summary,
)

from .common import FakeServer

# Wednesday 2026-10-21, 10:00 in Poland: during lesson 3 (09:50-10:35).
NOW = "2026-10-21T08:00:00+00:00"


@pytest.fixture(autouse=True)
def frozen_today(freezer: FrozenDateTimeFactory) -> None:
    """Freeze the time during a lesson."""
    freezer.move_to(NOW)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Set up the entry; return the timetable calendar entity id."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = er.async_get(hass).async_get_entity_id(
        "calendar", DOMAIN, f"{entry.entry_id}_timetable"
    )
    assert entity_id
    return entity_id


async def _events(hass: HomeAssistant, entity_id: str) -> list[dict[str, Any]]:
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": entity_id,
            "start_date_time": "2026-10-19T00:00:00+02:00",
            "end_date_time": "2026-11-16T00:00:00+01:00",
        },
        blocking=True,
        return_response=True,
    )
    return response[entity_id]["events"]


async def test_one_event_per_lesson_with_times_and_classroom(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Real lesson times (also after the DST change), classroom as location,
    changes in the title; empty periods give no event."""
    entity_id = await _setup(hass, config_entry)

    events = await _events(hass, entity_id)

    assert [
        (e["summary"], e["start"], e["end"], e.get("location")) for e in events
    ] == [
        (
            "Matematyka",
            "2026-10-19T08:00:00+02:00",
            "2026-10-19T08:45:00+02:00",
            "12",
        ),
        (
            "Język polski",
            "2026-10-19T08:55:00+02:00",
            "2026-10-19T09:40:00+02:00",
            "8",
        ),
        (
            "Matematyka (zastępstwo)",
            "2026-10-21T09:50:00+02:00",
            "2026-10-21T10:35:00+02:00",
            "12",
        ),
        (
            "Historia (odwołane)",
            "2026-10-27T09:50:00+01:00",
            "2026-10-27T10:35:00+01:00",
            "10",
        ),
        (
            "Język angielski (zmiana sali)",
            "2026-10-29T08:00:00+01:00",
            "2026-10-29T08:45:00+01:00",
            "21",
        ),
    ]


async def test_description_has_readable_lines_and_a_json_line(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The JSON line parses back to all fields, the change included."""
    entity_id = await _setup(hass, config_entry)
    events = {e["summary"]: e for e in await _events(hass, entity_id)}

    substitution = events["Matematyka (zastępstwo)"]["description"]
    assert substitution.splitlines()[:-1] == [
        "Nr lekcji: 3",
        "Przedmiot: Matematyka",
        "Nauczyciel: Zenon Zastępczy",
        "Sala: 12",
        "Zmiana: zastępstwo (Nauczyciel: Adam Rachunek -> Zenon Zastępczy; "
        "Data dodania: 2026-10-18 12:00:00)",
    ]
    assert json.loads(substitution.splitlines()[-1])["librus_apix"] == 1
    assert parse_description(substitution) == {
        "id": "2026-10-21/3",
        "date": "2026-10-21",
        "lesson": 3,
        "start": "09:50",
        "end": "10:35",
        "subject": "Matematyka",
        "teacher": "Zenon Zastępczy",
        "classroom": "12",
        "cancelled": False,
        "changes": [
            {
                "type": "zastępstwo",
                "teacher_swap": "Adam Rachunek -> Zenon Zastępczy",
                "subject_swap": "",
                "classroom_swap": "",
                "date_added": "2026-10-18 12:00:00",
            }
        ],
    }

    cancelled = events["Historia (odwołane)"]["description"]
    assert "Zmiana: odwołane" in cancelled.splitlines()
    fields = parse_description(cancelled)
    assert fields["cancelled"] is True
    assert [change["type"] for change in fields["changes"]] == ["odwołane"]

    plain = parse_description(events["Matematyka"]["description"])
    assert (plain["cancelled"], plain["changes"]) == (False, [])


@pytest.mark.parametrize(
    ("language", "name"), [("en", "Timetable"), ("pl", "Plan lekcji")]
)
async def test_name_and_current_lesson(
    hass: HomeAssistant,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    language: str,
    name: str,
) -> None:
    """The calendar is named after the student; it is on during a lesson."""
    hass.config.language = language

    entity_id = await _setup(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.attributes["friendly_name"] == f"Zofia Testowa {name}"
    assert state.state == "on"
    assert state.attributes["message"] == "Matematyka (zastępstwo)"
    assert state.attributes["location"] == "12"


async def test_no_events_before_the_first_poll(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Without timetable data the calendar has no events."""
    mock_server.broken_weeks = {date(2026, 10, 19), date(2026, 10, 26)}
    await _setup(hass, config_entry)

    calendar = TimetableCalendar(config_entry.runtime_data.timetable)

    assert calendar._events() == []


def test_summary_lists_every_change() -> None:
    """Several notices on one lesson are all in the title."""
    lesson = Lesson(
        date(2026, 10, 21),
        2,
        "08:55",
        "09:40",
        "Fizyka",
        "Iza Atomowa",
        "101",
        (LessonChange("zastępstwo"), LessonChange("zmiana sali")),
    )

    assert summary(lesson) == "Fizyka (zastępstwo, zmiana sali)"


def test_description_without_teacher_and_classroom() -> None:
    """Lines Librus gives no value for are left out."""
    lesson = Lesson(date(2026, 10, 21), 1, "08:00", "08:45", "Fizyka", "", "")

    lines = describe(lesson).splitlines()

    assert lines[:-1] == ["Nr lekcji: 1", "Przedmiot: Fizyka"]
    assert parse_description(lines[-1])["classroom"] == ""


@pytest.mark.parametrize(("start", "end"), [("", "08:45"), ("09:00", "08:45")])
def test_lesson_without_valid_times_is_all_day(start: str, end: str) -> None:
    """Missing or reversed times give an all-day event."""
    lesson = Lesson(date(2026, 10, 21), 1, start, end, "Fizyka", "", "")

    assert lesson_times(lesson) == (date(2026, 10, 21), date(2026, 10, 22))


def test_calendar_base_needs_events() -> None:
    """Subclasses provide the events."""
    calendar = LibrusCalendar(MagicMock(), "x")

    with pytest.raises(NotImplementedError):
        calendar._events()
