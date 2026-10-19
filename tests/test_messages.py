"""Tests for the messages sensor and the new_message event (F7)."""

from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from librus_apix.messages import Message
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)
import requests_mock as rm

from custom_components.librus_apix.const import CONF_MESSAGE_COUNT, DOMAIN
from custom_components.librus_apix.coordinator import (
    librus_datetime,
    message_id,
    read_messages,
)
from custom_components.librus_apix.sensor import MessagesSensor

from .common import (
    MOCK_URL,
    FakeMessage,
    FakeServer,
    default_messages,
    info_page,
    messages_page,
)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, domain: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_messages"
    )
    assert entity_id
    return entity_id


def _fired(hass: HomeAssistant, events: list, entity_id: str) -> list[dict[str, Any]]:
    return [
        dict(e.data["new_state"].attributes)
        for e in events
        if e.data["entity_id"] == entity_id
        and e.data["new_state"].attributes.get(ATTR_EVENT_TYPE)
    ]


async def test_sensor_shows_unread_count_and_list(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """State = unread count; the attribute lists the messages with details."""
    await _setup(hass, config_entry)

    state = hass.states.get(_entity_id(hass, config_entry, "sensor"))
    assert state.state == "2"
    messages = state.attributes["messages"]
    assert len(messages) == 8
    assert messages[0] == {
        "id": "5001",
        "author": "Nauczyciel 0",
        "title": "Temat 0",
        "date": "2026-10-18T12:00:00+02:00",
        "unread": True,
        "has_attachment": False,
        "content_cached": False,
    }
    assert messages[1]["has_attachment"] is True
    assert messages[2]["unread"] is False


def test_message_list_is_not_recorded() -> None:
    """The list stays out of the recorder."""
    assert "messages" in MessagesSensor._unrecorded_attributes


@pytest.mark.parametrize(
    ("count", "list_requests"),
    [(1, 1), (3, 1), (5, 1), (7, 2), (100, 2)],
)
async def test_message_count_option_sets_the_list_length(
    hass: HomeAssistant,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    count: int,
    list_requests: int,
) -> None:
    """Only as many list pages as needed for the count are read (5 per page)."""
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, CONF_MESSAGE_COUNT: count}
    )

    await _setup(hass, config_entry)

    state = hass.states.get(_entity_id(hass, config_entry, "sensor"))
    assert len(state.attributes["messages"]) == min(count, 8)
    assert mock_server.paths().count("/wiadomosci/1/5") == list_requests


async def test_no_message_body_is_requested(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Polling reads list pages only, so no message is marked read."""
    await _setup(hass, config_entry)
    await config_entry.runtime_data.messages.async_refresh()

    assert set(mock_server.paths()) == {"/informacja", "/wiadomosci/1/5"}


async def test_new_messages_fire_one_event_each_in_time_order(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The first poll fires nothing; 3 new messages fire 3 events, oldest first."""
    events = async_capture_events(hass, EVENT_STATE_CHANGED)
    await _setup(hass, config_entry)
    event_id = _entity_id(hass, config_entry, "event")
    assert _fired(hass, events, event_id) == []

    mock_server.messages[:0] = [
        FakeMessage(6003, "Sekretariat", "C", "2026-10-19 10:02:00", unread=True),
        FakeMessage(6002, "Sekretariat", "B", "2026-10-19 10:01:00", unread=True),
        FakeMessage(6001, "Dyrektor", "A", "2026-10-19 10:00:00", attachment=True),
    ]
    await config_entry.runtime_data.messages.async_refresh()
    await hass.async_block_till_done()

    fired = _fired(hass, events, event_id)
    assert [(f[ATTR_EVENT_TYPE], f["id"]) for f in fired] == [
        ("new_message", "6001"),
        ("new_message", "6002"),
        ("new_message", "6003"),
    ]
    expected = {
        "event_type": "new_message",
        "id": "6001",
        "author": "Dyrektor",
        "title": "A",
        "date": "2026-10-19T10:00:00+02:00",
        "unread": False,
        "has_attachment": True,
        "student": "Zofia Testowa",
        "config_entry_id": config_entry.entry_id,
    }
    assert expected.items() <= fired[0].items()
    assert not {"body", "content"} & fired[0].keys()


async def test_reload_does_not_fire_again(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """After a reload only messages that arrived meanwhile fire."""
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    mock_server.messages.insert(0, FakeMessage(6001, "A", "New", "2026-10-19 10:00:00"))
    events = async_capture_events(hass, EVENT_STATE_CHANGED)

    await _setup(hass, config_entry)

    fired = _fired(hass, events, _entity_id(hass, config_entry, "event"))
    assert [f["id"] for f in fired] == ["6001"]


async def test_broken_message_page_does_not_block_the_setup(
    hass: HomeAssistant, requests_mock: rm.Mocker, config_entry: MockConfigEntry
) -> None:
    """Messages fail: the entry loads, only the message entities are unavailable."""
    requests_mock.get(f"{MOCK_URL}/informacja", text=info_page())
    requests_mock.get(f"{MOCK_URL}/wiadomosci/1/5", status_code=500, text="")

    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(_entity_id(hass, config_entry, "sensor")).state == (
        STATE_UNAVAILABLE
    )
    assert hass.states.get(_entity_id(hass, config_entry, "event")).state == (
        STATE_UNAVAILABLE
    )


def test_page_without_pagination_is_the_only_page() -> None:
    """Without a page counter only the first page is read."""
    client = MagicMock()
    page = messages_page(default_messages()[:2], 0)
    client.get.return_value.text = page.split('<div class="pagination">')[0]

    messages = read_messages(client, 20)

    assert [m.href for m in messages] == ["5001", "5002"]
    client.post.assert_not_called()


def test_librus_datetime() -> None:
    """Librus times become ISO 8601 in Polish time; other text stays."""
    assert librus_datetime("2026-01-05 07:30:00") == "2026-01-05T07:30:00+01:00"
    assert librus_datetime(" 2026-07-05 07:30:00 ") == "2026-07-05T07:30:00+02:00"
    assert librus_datetime("wczoraj") == "wczoraj"


def test_message_without_link_gets_an_id() -> None:
    """A message without a link is identified by author, title and date."""
    message = Message("A", "T", "2026-10-19 10:00:00", "", False, False)

    assert message_id(message) == "A|T|2026-10-19 10:00:00"
