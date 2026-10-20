"""Tests for the get_message_content action (F7)."""

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.api import LibrusApi
from custom_components.librus_apix.const import DOMAIN
from custom_components.librus_apix.exceptions import LibrusConnectionError

from .common import MOCK_URL, FakeServer


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Set up the entry; return the messages sensor id."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_messages"
    )
    assert entity_id
    return entity_id


async def _get(hass: HomeAssistant, entity_id: str, msg_id: str) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN,
        "get_message_content",
        {"entity_id": entity_id, "message_id": msg_id},
        blocking=True,
        return_response=True,
    )


def _listed(hass: HomeAssistant, entity_id: str, msg_id: str) -> dict[str, Any]:
    messages = hass.states.get(entity_id).attributes["messages"]
    return next(m for m in messages if m["id"] == msg_id)


async def test_returns_details_content_and_attachments(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The response has author, title, date, content and attachment names."""
    entity_id = await _setup(hass, config_entry)

    response = await _get(hass, entity_id, "5002")

    assert response == {
        "id": "5002",
        "author": "Nauczyciel 1",
        "title": "Temat 1",
        "date": "2026-10-17T12:01:00+02:00",
        "content": "Treść wiadomości.\nDruga linia.",
        "attachments": ["Plan_lekcji.pdf", "Zgoda.docx"],
    }


async def test_second_call_makes_no_request(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The content is read from Librus once, then from the store."""
    entity_id = await _setup(hass, config_entry)

    first = await _get(hass, entity_id, " 5002 ")
    second = await _get(hass, entity_id, "5002")

    assert first == second
    assert mock_server.paths().count("/wiadomosci/1/5/5002") == 1


async def test_read_message_is_marked_read_and_cached(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """After the read: unread false, content_cached true, one unread less."""
    entity_id = await _setup(hass, config_entry)
    assert _listed(hass, entity_id, "5001")["unread"] is True
    assert _listed(hass, entity_id, "5001")["content_cached"] is False
    assert hass.states.get(entity_id).state == "2"

    await _get(hass, entity_id, "5001")
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _listed(hass, entity_id, "5001")["unread"] is False
    assert _listed(hass, entity_id, "5001")["content_cached"] is True
    assert hass.states.get(entity_id).state == "1"


async def test_cache_survives_a_reload_and_is_pruned(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A cached body stays after a reload; it goes when the message leaves the list."""
    entity_id = await _setup(hass, config_entry)
    await _get(hass, entity_id, "5008")
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    await _get(hass, entity_id, "5008")
    assert mock_server.paths().count("/wiadomosci/1/5/5008") == 1

    mock_server.messages = [m for m in mock_server.messages if m.id != 5008]
    await config_entry.runtime_data.messages.async_refresh()
    assert "5008" not in config_entry.runtime_data.messages.bodies


async def test_unknown_message_id(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """An id that is not on the list is a translated validation error."""
    entity_id = await _setup(hass, config_entry)

    with pytest.raises(ServiceValidationError) as exc:
        await _get(hass, entity_id, "9999")

    assert exc.value.translation_key == "unknown_message"
    assert exc.value.translation_placeholders == {"message_id": "9999"}
    assert "/wiadomosci/1/5/9999" not in mock_server.paths()


@pytest.mark.parametrize("entity_id", ["sensor.unknown", "sun.sun"])
async def test_entity_of_another_integration(
    hass: HomeAssistant,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    entity_id: str,
) -> None:
    """Only entities of a loaded HALibrus entry are accepted."""
    await _setup(hass, config_entry)
    er.async_get(hass).async_get_or_create(
        "sun", "sun", "sun", suggested_object_id="sun"
    )

    with pytest.raises(ServiceValidationError) as exc:
        await _get(hass, entity_id, "5001")

    assert exc.value.translation_key == "invalid_entity"


async def test_entry_not_loaded(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """An unloaded entry cannot read messages."""
    entity_id = await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)

    with pytest.raises(ServiceValidationError) as exc:
        await _get(hass, entity_id, "5001")

    assert exc.value.translation_key == "invalid_entity"


async def test_librus_error_while_reading(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A Librus failure is a translated error and nothing is cached."""
    entity_id = await _setup(hass, config_entry)

    with (
        patch.object(LibrusApi, "async_call", side_effect=LibrusConnectionError("x")),
        pytest.raises(HomeAssistantError) as exc,
    ):
        await _get(hass, entity_id, "5001")

    assert exc.value.translation_key == "cannot_read_message"
    assert "5001" not in config_entry.runtime_data.messages.bodies


async def test_broken_message_page(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A page without the message table is a read error."""
    entity_id = await _setup(hass, config_entry)
    mock_server.mocker.get(f"{MOCK_URL}/wiadomosci/1/5/5003", text="<p>?</p>")

    with pytest.raises(HomeAssistantError) as exc:
        await _get(hass, entity_id, "5003")

    assert exc.value.translation_key == "cannot_read_message"
