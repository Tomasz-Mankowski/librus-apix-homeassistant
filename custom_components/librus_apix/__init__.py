"""The Librus APIX integration."""

import logging

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import LibrusApi
from .const import CONF_SERVER_URL
from .coordinator import LibrusConfigEntry, LibrusData, StudentInfoCoordinator
from .store import LibrusStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> bool:
    """Set up one student: storage, coordinators, platforms."""
    _LOGGER.debug("Setting up entry %s", entry.entry_id)
    api = LibrusApi(
        hass,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        base_url=entry.data.get(CONF_SERVER_URL),
    )
    store = LibrusStore(hass, entry.entry_id)
    await store.async_load()
    student = StudentInfoCoordinator(hass, entry, api)
    await student.async_config_entry_first_refresh()
    entry.runtime_data = LibrusData(api=api, store=store, student=student)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> bool:
    """Unload the platforms and close the HTTP session."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.async_add_executor_job(entry.runtime_data.api.close)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> None:
    """Delete the stored data of a removed entry."""
    await LibrusStore(hass, entry.entry_id).async_remove()
