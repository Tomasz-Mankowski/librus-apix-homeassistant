"""Tests for the schedule calendar (F4, F5)."""

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from librus_apix.schedule import Event
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.const import CONF_TIMEFRAME, DOMAIN
from custom_components.librus_apix.schedule import (
    ScheduleEvent,
    _event_id,
    describe,
    event_times,
    months_in_range,
    parse_description,
)

from .common import FakeEvent, FakeServer

NOW = "2026-10-19T08:00:00+00:00"


@pytest.fixture(autouse=True)
def frozen_today(freezer: FrozenDateTimeFactory) -> None:
    """Monday 2026-10-19 in Poland."""
    freezer.move_to(NOW)


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry, timeframe: int = 1
) -> str:
    """Set up the entry; return the calendar entity id."""
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_TIMEFRAME: timeframe}
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = er.async_get(hass).async_get_entity_id(
        "calendar", DOMAIN, f"{entry.entry_id}_schedule"
    )
    assert entity_id
    return entity_id


async def _events(hass: HomeAssistant, entity_id: str) -> list[dict[str, Any]]:
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": entity_id,
            "start_date_time": "2026-10-01T00:00:00+02:00",
            "end_date_time": "2027-03-01T00:00:00+01:00",
        },
        blocking=True,
        return_response=True,
    )
    return response[entity_id]["events"]


def _detail_requests(server: FakeServer) -> int:
    return sum("/terminarz/szczegoly" in path for path in server.paths())


@pytest.mark.parametrize(
    ("today", "timeframe", "months"),
    [
        (date(2026, 10, 19), 0, [(2026, 10)]),
        (date(2026, 10, 19), 1, [(2026, 10), (2026, 11)]),
        (date(2026, 12, 31), 2, [(2026, 12), (2027, 1), (2027, 2)]),
        (date(2027, 1, 1), 6, [(2027, m) for m in range(1, 8)]),
    ],
)
def test_months_in_range(
    today: date, timeframe: int, months: list[tuple[int, int]]
) -> None:
    """Current month plus N months, across the new year."""
    assert months_in_range(today, timeframe) == months


async def test_events_of_the_timeframe_with_lesson_times(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """October and November; lesson times from the bells, others all-day or 1 h."""
    entity_id = await _setup(hass, config_entry)

    events = {e["summary"]: e for e in await _events(hass, entity_id)}

    assert list(events) == [
        "Sprawdzian: Matematyka",
        "Wycieczka: Muzeum Techniki",
        "Zebranie z rodzicami",
        "Klasówka: Historia",
        "Dzień wolny: Wolne",
    ]
    assert events["Sprawdzian: Matematyka"]["start"] == "2026-10-21T09:50:00+02:00"
    assert events["Sprawdzian: Matematyka"]["end"] == "2026-10-21T10:35:00+02:00"
    assert events["Wycieczka: Muzeum Techniki"]["start"] == "2026-10-23"
    assert events["Wycieczka: Muzeum Techniki"]["end"] == "2026-10-24"
    assert events["Zebranie z rodzicami"]["start"] == "2026-10-28T17:00:00+01:00"
    assert events["Zebranie z rodzicami"]["end"] == "2026-10-28T18:00:00+01:00"
    assert events["Klasówka: Historia"]["start"] == "2026-11-04T08:55:00+01:00"


async def test_larger_timeframe_adds_months(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Timeframe 2 adds December; lesson 9 has no bell time, so it is all-day."""
    entity_id = await _setup(hass, config_entry, timeframe=2)

    events = {e["summary"]: e for e in await _events(hass, entity_id)}

    assert events["Kartkówka: Przyroda"]["start"] == "2026-12-02"
    assert len(events) == 6


async def test_description_has_readable_lines_and_a_json_line(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The JSON line parses back to all fields of the event."""
    entity_id = await _setup(hass, config_entry)
    [test] = [
        e for e in await _events(hass, entity_id) if e["summary"].startswith("Spr")
    ]

    lines = test["description"].splitlines()
    assert lines[0] == "Data: 2026-10-21"
    assert "Rodzaj: Sprawdzian" in lines
    assert "Opis: Ułamki zwykłe" in lines
    fields = parse_description(test["description"])
    assert fields == {
        "id": "szczegoly/3003",
        "date": "2026-10-21",
        "type": "Sprawdzian",
        "subject": "Matematyka",
        "teacher": "Adam Rachunek",
        "lesson": 3,
        "hour": None,
        "description": "Ułamki zwykłe",
        "date_added": "2026-10-01 12:00:00",
        "details": fields["details"],
    }
    assert fields["details"]["Nr lekcji"] == "3"


async def test_detail_pages_only_for_new_or_changed_events(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Details are read once; a changed or added event reads one more page."""
    await _setup(hass, config_entry)
    schedule = config_entry.runtime_data.schedule
    assert _detail_requests(mock_server) == 5

    await schedule.async_refresh()
    assert _detail_requests(mock_server) == 5

    mock_server.events[0].day = date(2026, 10, 22)
    mock_server.events.append(FakeEvent(3020, date(2026, 11, 9), "Konkurs"))
    await schedule.async_refresh()
    assert _detail_requests(mock_server) == 7


async def test_removed_event_leaves_the_cache(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Details of events that are no longer listed are dropped."""
    await _setup(hass, config_entry)
    mock_server.events = mock_server.events[1:]

    await config_entry.runtime_data.schedule.async_refresh()

    cache = config_entry.runtime_data.store.data["schedule_details"]
    assert "szczegoly/3003" not in cache
    assert "szczegoly/3005" in cache


async def test_next_event_is_the_calendar_state(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The calendar shows the next event."""
    entity_id = await _setup(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == "off"
    assert state.attributes["message"] == "Sprawdzian: Matematyka"
    assert state.attributes["friendly_name"] == "Zofia Testowa Schedule"


async def test_without_bell_times_lessons_are_all_day(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A broken timetable: lesson events become all-day; the entry still loads."""
    mock_server.mocker.post(
        "http://librus-mock-a:8000/przegladaj_plan_lekcji", text="<p>?</p>"
    )
    entity_id = await _setup(hass, config_entry)

    [test] = [
        e for e in await _events(hass, entity_id) if e["summary"].startswith("Spr")
    ]
    assert test["start"] == "2026-10-21"
    assert config_entry.runtime_data.student.data.bells == {}


def test_event_without_link_gets_a_stable_id() -> None:
    """Without a link the id is a hash of date, subject, title and lesson."""
    event = Event("Sprawdzian", "Matematyka", {}, "21", 3, "unknown", "")

    first = _event_id(event, date(2026, 10, 21))

    assert first == _event_id(event, date(2026, 10, 21))
    assert first != _event_id(event, date(2026, 10, 22))
    assert "/" not in first


@pytest.mark.parametrize(
    "text",
    ["Rodzaj: Sprawdzian", "Rodzaj: X\n{not json", 'Rodzaj: X\n{"other": 1}', ""],
)
def test_description_without_our_json_line(text: str) -> None:
    """Text without our JSON line gives None."""
    assert parse_description(text) is None


def _event(**changes: Any) -> ScheduleEvent:
    base = {
        "id": "szczegoly/1",
        "day": date(2026, 10, 21),
        "lesson": None,
        "hour": None,
        "list_subject": "Matematyka",
        "list_title": "Sprawdzian",
        "data": {"Nauczyciel": "Adam Rachunek", "Opis": "Ułamki"},
    }
    return ScheduleEvent(**{**base, **changes})


def test_without_a_detail_page_the_list_data_is_used() -> None:
    """Description lines and fields come from the calendar list."""
    event = _event()

    assert event.type == "Sprawdzian"
    assert event.subject == "Matematyka"
    assert describe(event).splitlines()[:3] == [
        "Rodzaj: Sprawdzian",
        "Nauczyciel: Adam Rachunek",
        "Opis: Ułamki",
    ]


def test_unknown_values_are_empty() -> None:
    """The library writes "unknown" for missing values."""
    event = _event(detail={"Rodzaj": "Test", "Nauczyciel": "unknown"})

    assert event.teacher == ""
    assert event.subject == ""


def test_bad_bell_times_fall_back_to_the_hour_or_all_day() -> None:
    """Times that are not HH:MM are not used."""
    bells = {2: ("8.00", "8.45")}

    assert event_times(_event(lesson=2), bells) == (
        date(2026, 10, 21),
        date(2026, 10, 22),
    )
    start, end = event_times(_event(lesson=2, hour="17:30"), bells)
    assert (start.hour, start.minute, (end - start).seconds) == (17, 30, 3600)


async def test_broken_detail_page_keeps_the_event(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A detail page that cannot be read leaves the list data."""
    mock_server.mocker.get(
        "http://librus-mock-a:8000/terminarz/szczegoly/3003", text="<p>?</p>"
    )
    entity_id = await _setup(hass, config_entry)

    [test] = [
        e for e in await _events(hass, entity_id) if e["summary"].startswith("Spr")
    ]
    assert test["summary"] == "Sprawdzian: Matematyka"
    assert parse_description(test["description"])["details"] == {}


async def test_lesson_changes_without_a_detail_page(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Substitution and cancelled lesson: type, subject, teacher, lesson times (I-004)."""
    mock_server.events += [
        FakeEvent(
            0,
            date(2026, 10, 22),
            "",
            "Anna Zastępcza",
            subject="Informatyka",
            lesson=2,
            kind="substitution",
        ),
        FakeEvent(
            0,
            date(2026, 10, 26),
            "",
            "Jan Nieobecny",
            subject="Edukacja wczesnoszkolna",
            lesson=3,
            kind="cancelled",
        ),
    ]
    entity_id = await _setup(hass, config_entry)

    events = {e["summary"]: e for e in await _events(hass, entity_id)}
    substitution = events["Zastępstwo: Informatyka"]
    cancelled = events["Odwołane zajęcia: Edukacja wczesnoszkolna"]
    assert substitution["start"] == "2026-10-22T08:55:00+02:00"
    assert cancelled["start"] == "2026-10-26T09:50:00+01:00"
    assert substitution["description"].splitlines()[:-1] == [
        "Rodzaj: Zastępstwo",
        "Przedmiot: Informatyka",
        "Nauczyciel: Anna Zastępcza",
    ]
    fields = parse_description(cancelled["description"])
    assert {
        k: fields[k] for k in ("type", "subject", "teacher", "lesson", "details")
    } == {
        "type": "Odwołane zajęcia",
        "subject": "Edukacja wczesnoszkolna",
        "teacher": "Jan Nieobecny",
        "lesson": 3,
        "details": {},
    }
    assert _detail_requests(mock_server) == 5


@pytest.mark.parametrize(
    ("list_subject", "list_title", "expected"),
    [
        (
            "Zastępstwo z Anna Zastępcza na lekcji nr: 10 (Język polski)",
            "Zastępstwo z Anna Zastępcza na lekcji nr: 10 (Język polski)",
            ("Zastępstwo", "Język polski", "Anna Zastępcza"),
        ),
        (
            "Odwołane zajęcia",
            "Jan Nieobecny na lekcji nr: 5 (Wychowanie fizyczne (chłopcy))",
            ("Odwołane zajęcia", "Wychowanie fizyczne (chłopcy)", "Jan Nieobecny"),
        ),
        (
            "Jan Nieobecny na lekcji nr: 5 (Informatyka)",
            "Jan Nieobecny na lekcji nr: 5 (Informatyka)",
            ("Jan Nieobecny na lekcji nr: 5 (Informatyka)", "", ""),
        ),
        (
            "Matematyka",
            "Sprawdzian na lekcji nr: 5",
            ("Sprawdzian na lekcji nr: 5", "Matematyka", ""),
        ),
    ],
    ids=["substitution", "cancelled", "no kind: as listed", "no pattern"],
)
def test_lesson_change_from_the_list_text(
    list_subject: str, list_title: str, expected: tuple[str, str, str]
) -> None:
    """Only the Librus patterns of lesson changes are split (D-104)."""
    event = _event(list_subject=list_subject, list_title=list_title, data={})

    assert (event.type, event.subject, event.teacher) == expected


def test_a_detail_page_wins_over_the_list_text() -> None:
    """With a detail page the list text is not parsed."""
    event = _event(
        list_title="Zastępstwo z Anna Zastępcza na lekcji nr: 1 (Fizyka)",
        detail={
            "Rodzaj": "Sprawdzian",
            "Przedmiot": "Fizyka",
            "Nauczyciel": "Adam Rachunek",
        },
    )

    assert (event.type, event.subject, event.teacher) == (
        "Sprawdzian",
        "Fizyka",
        "Adam Rachunek",
    )


def test_without_a_detail_page_and_subject_only_the_type_line() -> None:
    """No subject and no teacher: just the type, then the JSON line."""
    event = _event(list_subject="Wycieczka", list_title="Wycieczka", data={})

    assert describe(event).splitlines()[0] == "Rodzaj: Wycieczka"
    assert len(describe(event).splitlines()) == 2
