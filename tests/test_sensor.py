"""Tests for the student information sensors."""

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.const import DOMAIN

from .common import FakeServer


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    return hass.states.get(entity_id).state


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_no_lucky_number_is_unknown(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Without a lucky number on the page the sensor is unknown."""
    mock_server.lucky = None

    await _setup(hass, config_entry)

    assert _state(hass, config_entry, "lucky_number") == STATE_UNKNOWN


async def test_long_school_name_is_cut_to_the_state_limit(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A state is at most 255 characters."""
    mock_server.school = "S" * 300

    await _setup(hass, config_entry)

    assert _state(hass, config_entry, "school") == "S" * 255


async def test_values_follow_the_coordinator(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A new lucky number appears after the next refresh."""
    await _setup(hass, config_entry)
    assert _state(hass, config_entry, "lucky_number") == "7"

    mock_server.lucky = "21"
    await config_entry.runtime_data.student.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert _state(hass, config_entry, "lucky_number") == "21"
