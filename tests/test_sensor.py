"""Tests for the student information and lucky-number sensors."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

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


async def test_lucky_number_has_its_own_poll(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The lucky-number poll reads only the information page (F4).

    The first lucky number comes from the student-info poll of the setup; later
    the lucky number follows only its own poll.
    """
    await _setup(hass, config_entry)
    assert mock_server.paths().count("/informacja") == 1
    assert _state(hass, config_entry, "lucky_number") == "7"
    data = config_entry.runtime_data
    mock_server.lucky = "21"

    start = len(mock_server.paths())
    await data.student.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_server.paths()[start:] == ["/informacja", "/przegladaj_plan_lekcji"]
    assert _state(hass, config_entry, "lucky_number") == "7"

    start = len(mock_server.paths())
    await data.lucky_number.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_server.paths()[start:] == ["/informacja"]
    assert _state(hass, config_entry, "lucky_number") == "21"


async def test_lucky_number_polls_after_its_interval(
    hass: HomeAssistant,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The first lucky-number poll comes one interval (180 min) after the setup."""
    await _setup(hass, config_entry)
    mock_server.lucky = "21"

    freezer.tick(timedelta(minutes=179))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_server.paths().count("/informacja") == 1
    assert _state(hass, config_entry, "lucky_number") == "7"

    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_server.paths().count("/informacja") == 2
    assert _state(hass, config_entry, "lucky_number") == "21"
