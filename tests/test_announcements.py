"""Tests for the announcements sensor and the new_announcement event (F9)."""

from typing import Any

from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from librus_apix.announcements import Announcement
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.librus_apix.const import DOMAIN
from custom_components.librus_apix.coordinator import announcement_id
from custom_components.librus_apix.event import AnnouncementsEvent
from custom_components.librus_apix.sensor import AnnouncementsSensor

from .common import FakeAnnouncement, FakeServer


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, domain: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_announcements"
    )
    assert entity_id
    return entity_id


def _fired(events: list, entity_id: str) -> list[dict[str, Any]]:
    return [
        dict(e.data["new_state"].attributes)
        for e in events
        if e.data["entity_id"] == entity_id
        and e.data["new_state"].attributes.get(ATTR_EVENT_TYPE)
    ]


async def test_sensor_shows_all_announcements(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """State = number of announcements; each with title, author, date, full text."""
    await _setup(hass, config_entry)

    state = hass.states.get(_entity_id(hass, config_entry, "sensor"))
    assert state.state == "3"
    first = state.attributes["announcements"][0]
    assert first == {
        "id": first["id"],
        "title": "Zebrania z rodzicami",
        "author": "Dyrektor Szkoły",
        "date": "2026-10-16",
        "content": "Zebrania odbędą się w środę o 17:00.\nSale według listy.",
    }
    assert [a["title"] for a in state.attributes["announcements"]] == [
        "Zebrania z rodzicami",
        "Zbiórka makulatury",
        "Szczepienia",
    ]


async def test_no_announcements(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The 'no announcements' page gives 0."""
    mock_server.announcements = []

    await _setup(hass, config_entry)

    state = hass.states.get(_entity_id(hass, config_entry, "sensor"))
    assert state.state == "0"
    assert state.attributes["announcements"] == []


def test_texts_are_not_recorded() -> None:
    """The list and the event text stay out of the recorder."""
    assert "announcements" in AnnouncementsSensor._unrecorded_attributes
    assert "content" in AnnouncementsEvent._unrecorded_attributes


async def test_new_announcements_fire_one_event_each(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The first poll fires nothing; 2 new announcements fire 2 events, oldest first."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)
    await _setup(hass, config_entry)
    event_id = _entity_id(hass, config_entry, "event")
    assert _fired(events, event_id) == []

    mock_server.announcements[:0] = [
        FakeAnnouncement("Dni otwarte", "Dyrektor", "2026-10-19", "Zapraszamy."),
        FakeAnnouncement("Biblioteka", "Bibliotekarka", "2026-10-18", "Nowe godziny."),
    ]
    await config_entry.runtime_data.announcements.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    fired = _fired(events, event_id)
    assert [(f[ATTR_EVENT_TYPE], f["title"]) for f in fired] == [
        ("new_announcement", "Biblioteka"),
        ("new_announcement", "Dni otwarte"),
    ]
    assert fired[1]["content"] == "Zapraszamy."
    assert fired[1]["student"] == "Zofia Testowa"
    assert fired[1]["config_entry_id"] == config_entry.entry_id


def test_announcement_id_is_stable() -> None:
    """Same title, author and date give the same id; another date another id."""
    one = Announcement("T", "A", "text", "2026-10-19")
    same = Announcement(" T ", "A", "edited text", "2026-10-19")
    other = Announcement("T", "A", "text", "2026-10-20")

    assert announcement_id(one) == announcement_id(same)
    assert announcement_id(one) != announcement_id(other)
    assert len(announcement_id(one)) == 16
