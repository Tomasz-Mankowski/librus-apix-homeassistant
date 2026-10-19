"""Tests for the schedule events: new_event and changed_event (F5, F17)."""

from datetime import date
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.librus_apix.const import CONF_TIMEFRAME, DOMAIN

from .common import FakeEvent, FakeServer


@pytest.fixture(autouse=True)
def frozen_today(freezer: FrozenDateTimeFactory) -> FrozenDateTimeFactory:
    """Monday 2026-10-19 in Poland."""
    freezer.move_to("2026-10-19T08:00:00+00:00")
    return freezer


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> list:
    """Set up the entry; return the captured state changes."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return events


async def _poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.schedule.async_refresh()
    await hass.async_block_till_done()


async def _reload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


def _fired(hass: HomeAssistant, entry: MockConfigEntry, events: list) -> list[dict]:
    entity_id = er.async_get(hass).async_get_entity_id(
        "event", DOMAIN, f"{entry.entry_id}_schedule"
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
    """Events that exist at the first poll are baseline."""
    events = await _setup(hass, config_entry)

    assert _fired(hass, config_entry, events) == []


async def test_new_event_carries_all_details_and_the_student(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A new event fires new_event with its fields, calendar times and student."""
    events = await _setup(hass, config_entry)
    mock_server.events.append(
        FakeEvent(
            3020,
            date(2026, 11, 9),
            "Kartkówka",
            description="Mapa",
            subject="Przyroda",
            lesson=1,
        )
    )

    await _poll(hass, config_entry)

    [fired] = _fired(hass, config_entry, events)
    assert _subset(
        fired,
        {
            "event_type": "new_event",
            "id": "szczegoly/3020",
            "date": "2026-11-09",
            "type": "Kartkówka",
            "subject": "Przyroda",
            "teacher": "Adam Rachunek",
            "lesson": 1,
            "hour": None,
            "description": "Mapa",
            "date_added": "2026-10-01 12:00:00",
            "summary": "Kartkówka: Przyroda",
            "start": "2026-11-09T08:00:00+01:00",
            "end": "2026-11-09T08:45:00+01:00",
            "all_day": False,
            "student": "Zofia Testowa",
            "config_entry_id": config_entry.entry_id,
        },
    )
    assert fired["details"]["Rodzaj"] == "Kartkówka"


async def test_moved_event_fires_changed_event_with_old_values(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A new date fires changed_event with the old values and the changed fields."""
    events = await _setup(hass, config_entry)
    mock_server.events[0].day = date(2026, 10, 22)

    await _poll(hass, config_entry)

    [fired] = _fired(hass, config_entry, events)
    assert _subset(
        fired,
        {
            "event_type": "changed_event",
            "id": "szczegoly/3003",
            "date": "2026-10-22",
            "start": "2026-10-22T09:50:00+02:00",
            "changed": ["date"],
        },
    )
    assert fired["old"] == {
        "date": "2026-10-21",
        "lesson": 3,
        "hour": None,
        "type": "Sprawdzian",
        "subject": "Matematyka",
        "teacher": "Adam Rachunek",
        "description": "Ułamki zwykłe",
    }


async def test_event_moved_to_the_next_month_is_a_change(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The same link in another covered month is the same event."""
    events = await _setup(hass, config_entry)
    mock_server.events[0].day = date(2026, 11, 3)
    mock_server.events[0].description = "Ułamki dziesiętne"

    await _poll(hass, config_entry)

    [fired] = _fired(hass, config_entry, events)
    assert fired["event_type"] == "changed_event"
    assert fired["changed"] == ["date", "description"]


async def test_unchanged_poll_fires_nothing(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A second poll with the same data fires nothing."""
    events = await _setup(hass, config_entry)

    await _poll(hass, config_entry)

    assert _fired(hass, config_entry, events) == []


async def test_larger_timeframe_and_restart_fire_nothing(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Timeframe 1 -> 3 adds December and January as baseline; a reload is quiet."""
    mock_server.events.append(FakeEvent(3030, date(2027, 1, 12), "Wycieczka"))
    events = await _setup(hass, config_entry)

    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, CONF_TIMEFRAME: 3}
    )
    await _reload(hass, config_entry)
    await _reload(hass, config_entry)

    assert len(config_entry.runtime_data.schedule.data.events) == 7
    assert _fired(hass, config_entry, events) == []


async def test_new_event_in_an_added_month_fires_after_the_baseline(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """After the larger timeframe is baseline, new events there fire."""
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, CONF_TIMEFRAME: 0}
    )
    events = await _setup(hass, config_entry)
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, CONF_TIMEFRAME: 1}
    )
    await _reload(hass, config_entry)
    assert _fired(hass, config_entry, events) == []

    mock_server.events.append(FakeEvent(3031, date(2026, 11, 20), "Konkurs"))
    await _poll(hass, config_entry)

    [fired] = _fired(hass, config_entry, events)
    assert _subset(fired, {"event_type": "new_event", "id": "szczegoly/3031"})
    assert _subset(fired, {"start": "2026-11-20", "end": "2026-11-21", "all_day": True})


async def test_new_month_fires_nothing(
    hass: HomeAssistant,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    frozen_today: FrozenDateTimeFactory,
) -> None:
    """On 1 November the window moves to November-December: December is baseline."""
    events = await _setup(hass, config_entry)

    frozen_today.move_to("2026-11-01T08:00:00+00:00")
    await _poll(hass, config_entry)

    assert [m for m in config_entry.runtime_data.schedule.data.months] == [
        (2026, 11),
        (2026, 12),
    ]
    assert _fired(hass, config_entry, events) == []


async def test_two_new_events_fire_two_events_in_date_order(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Each new event is its own trigger."""
    events = await _setup(hass, config_entry)
    mock_server.events += [
        FakeEvent(3041, date(2026, 11, 12), "Konkurs"),
        FakeEvent(3040, date(2026, 10, 30), "Wycieczka", hour="09:00"),
    ]

    await _poll(hass, config_entry)

    fired = _fired(hass, config_entry, events)
    assert [f["id"] for f in fired] == ["szczegoly/3040", "szczegoly/3041"]
    assert fired[0]["start"] == "2026-10-30T09:00:00+01:00"
