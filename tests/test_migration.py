"""Tests for the migration of entries made by older versions (D-114)."""

from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.const import (
    CONF_INTERVAL_ANNOUNCEMENTS,
    CONF_INTERVAL_GRADES,
    CONF_INTERVAL_LUCKY_NUMBER,
    CONF_INTERVAL_MESSAGES,
    CONF_INTERVAL_SCHEDULE,
    CONF_INTERVAL_STUDENT,
    CONF_INTERVAL_TIMETABLE,
    CONF_MESSAGE_COUNT,
    CONF_SERVER_URL,
    CONF_TIMEFRAME,
    CONF_TIMETABLE_WEEKS,
    DOMAIN,
)

from .common import MOCK_URL

# Options of an entry made by 1.0.0 with the default settings.
OPTIONS_1_0 = {
    CONF_INTERVAL_STUDENT: 360,
    CONF_INTERVAL_GRADES: 15,
    CONF_INTERVAL_MESSAGES: 15,
    CONF_INTERVAL_ANNOUNCEMENTS: 15,
    CONF_INTERVAL_SCHEDULE: 60,
    CONF_TIMEFRAME: 1,
    CONF_MESSAGE_COUNT: 20,
}
# Options added by the migration to minor version 2, with their defaults.
ADDED_1_1 = {
    CONF_INTERVAL_LUCKY_NUMBER: 180,
    CONF_INTERVAL_TIMETABLE: 360,
    CONF_TIMETABLE_WEEKS: 1,
}


def _entry(
    hass: HomeAssistant, version: int = 1, minor_version: int = 1, **options: int
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Zofia Testowa",
        unique_id="zofia.testowa",
        data={
            CONF_USERNAME: "zofia.testowa",
            CONF_PASSWORD: "secret",
            CONF_SERVER_URL: MOCK_URL,
        },
        options={**OPTIONS_1_0, **options},
        version=version,
        minor_version=minor_version,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.usefixtures("mock_server")
async def test_old_default_moves_to_the_new_default(hass: HomeAssistant) -> None:
    """Student info 360 → 1440; lucky number and timetable options added."""
    entry = _entry(hass)

    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert (entry.version, entry.minor_version) == (1, 2)
    assert entry.options == {**OPTIONS_1_0, **ADDED_1_1, CONF_INTERVAL_STUDENT: 1440}
    data = entry.runtime_data
    assert data.student.update_interval == timedelta(minutes=1440)
    assert data.lucky_number.update_interval == timedelta(minutes=180)
    assert data.timetable.update_interval == timedelta(minutes=360)
    assert len(data.timetable.data.weeks) == 2


@pytest.mark.usefixtures("mock_server")
async def test_user_value_stays(hass: HomeAssistant) -> None:
    """A student-info interval set by the user is kept."""
    entry = _entry(hass, **{CONF_INTERVAL_STUDENT: 120, CONF_INTERVAL_GRADES: 30})

    await _setup(hass, entry)

    assert entry.minor_version == 2
    assert entry.options == {
        **OPTIONS_1_0,
        **ADDED_1_1,
        CONF_INTERVAL_STUDENT: 120,
        CONF_INTERVAL_GRADES: 30,
    }


@pytest.mark.usefixtures("mock_server")
async def test_newer_minor_version_loads_unchanged(hass: HomeAssistant) -> None:
    """An entry of a newer minor version (same major) loads as it is."""
    options = {**OPTIONS_1_0, CONF_INTERVAL_LUCKY_NUMBER: 30}
    entry = _entry(hass, minor_version=3, **options)

    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 3
    assert entry.options == options


async def test_newer_major_version_is_not_loaded(hass: HomeAssistant) -> None:
    """An entry made by a newer major version is refused (by Home Assistant)."""
    entry = _entry(hass, version=2)

    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert entry.options == OPTIONS_1_0
