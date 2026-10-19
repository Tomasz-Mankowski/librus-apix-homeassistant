"""Tests for the grade events: new_grade, grade_changed, final_grade (F11)."""

from typing import Any

from bs4 import BeautifulSoup
from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.librus_apix.const import DOMAIN
from custom_components.librus_apix.grades import read_corrections

from .common import FakeFinal, FakeGrade, FakeServer, default_subjects, grades_page


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> list:
    """Set up the entry; return the captured state changes."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return events


async def _poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.grades.async_refresh()
    await hass.async_block_till_done()


def _fired(hass: HomeAssistant, entry: MockConfigEntry, events: list) -> list[dict]:
    entity_id = er.async_get(hass).async_get_entity_id(
        "event", DOMAIN, f"{entry.entry_id}_grades"
    )
    return [
        dict(e.data["new_state"].attributes)
        for e in events
        if e.data["entity_id"] == entity_id
        and e.data["new_state"].attributes.get(ATTR_EVENT_TYPE)
    ]


def _subset(fired: dict[str, Any], expected: dict[str, Any]) -> bool:
    return expected.items() <= fired.items()


async def test_first_poll_fires_nothing(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Grades that exist at the first poll are baseline."""
    events = await _setup(hass, config_entry)

    assert _fired(hass, config_entry, events) == []


async def test_new_grade_carries_all_details(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A new grade fires new_grade with subject, grade, details and student."""
    events = await _setup(hass, config_entry)
    mock_server.subjects[1].semester1.append(
        FakeGrade(
            1250, "5+", "Recytacja", "2026-10-18", weight=2, comment="Pan Tadeusz"
        )
    )

    await _poll(hass, config_entry)

    [fired] = _fired(hass, config_entry, events)
    assert _subset(
        fired,
        {
            "event_type": "new_grade",
            "id": "1250",
            "subject": "Język polski",
            "grade": "5+",
            "value": 5.5,
            "category": "Recytacja",
            "weight": 2,
            "counts": True,
            "teacher": "Ewa Ortografia",
            "date": "2026-10-18",
            "comment": "Pan Tadeusz",
            "semester": 1,
            "is_correction": False,
            "original_grade": None,
            "student": "Zofia Testowa",
            "config_entry_id": config_entry.entry_id,
        },
    )


async def test_correction_is_a_new_grade_with_the_original(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A correction fires new_grade with is_correction and the corrected grade."""
    events = await _setup(hass, config_entry)
    polish = mock_server.subjects[1].semester1[0]
    polish.correction = FakeGrade(1260, "5", "Dyktando", "2026-10-18", weight=2)

    await _poll(hass, config_entry)

    [fired] = _fired(hass, config_entry, events)
    assert _subset(
        fired, {"event_type": "new_grade", "id": "1260", "is_correction": True}
    )
    assert _subset(fired["original_grade"], {"id": "1201", "grade": "4"})


async def test_changed_value_fires_grade_changed(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Another value of a known grade fires grade_changed with old and new."""
    events = await _setup(hass, config_entry)
    mock_server.subjects[0].semester1[1].grade = "5"

    await _poll(hass, config_entry)

    [fired] = _fired(hass, config_entry, events)
    assert _subset(
        fired,
        {
            "event_type": "grade_changed",
            "id": "1102",
            "subject": "Matematyka",
            "grade": "5",
            "old_grade": "4+",
        },
    )


async def test_semester_grade_fires_final_grade(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A new semester grade and a changed proposed grade fire final_grade."""
    events = await _setup(hass, config_entry)
    math = mock_server.subjects[0]
    math.finals[0].grade = "5"
    mock_server.subjects[1].finals.append(FakeFinal(1290, "I", "4"))

    await _poll(hass, config_entry)

    fired = sorted(_fired(hass, config_entry, events), key=lambda f: f["id"])
    assert _subset(
        fired[0],
        {
            "event_type": "final_grade",
            "id": "1190",
            "subject": "Matematyka",
            "grade": "5",
            "proposed": True,
            "period": "semester_1",
            "old_grade": "4",
        },
    )
    assert _subset(
        fired[1],
        {
            "event_type": "final_grade",
            "id": "1290",
            "subject": "Język polski",
            "grade": "4",
            "proposed": False,
            "category": "Śródroczna",
            "old_grade": None,
        },
    )


async def test_several_new_grades_fire_in_date_order(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """One event per grade, oldest first, also across subjects (F16)."""
    events = await _setup(hass, config_entry)
    mock_server.subjects[0].semester1.append(FakeGrade(1150, "3", date="2026-10-17"))
    mock_server.subjects[1].semester1.append(FakeGrade(1251, "2", date="2026-10-15"))
    mock_server.subjects[2].semester1.append(FakeGrade(1350, "6", date="2026-10-16"))

    await _poll(hass, config_entry)

    assert [f["id"] for f in _fired(hass, config_entry, events)] == [
        "1251",
        "1350",
        "1150",
    ]


async def test_reload_does_not_fire_again(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Known grades stay known after a reload."""
    events = await _setup(hass, config_entry)
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _fired(hass, config_entry, events) == []


def test_corrections_are_read_from_the_wrappers() -> None:
    """[old new] wrappers link a correction to its grade; single grades are not."""
    page = grades_page(default_subjects())

    assert read_corrections(BeautifulSoup(page, "lxml")) == {"1104": "1103"}
