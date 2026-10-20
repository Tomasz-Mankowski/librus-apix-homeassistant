"""The HALibrus integration."""

import logging

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import LibrusApi
from .const import (
    CONF_INTERVAL_STUDENT,
    CONF_SERVER_URL,
    DEFAULT_OPTIONS,
    DOMAIN,
    NEW_OPTIONS_1_1,
    OLD_DEFAULT_INTERVAL_STUDENT,
)
from .coordinator import (
    AnnouncementsCoordinator,
    GradesCoordinator,
    LibrusConfigEntry,
    LibrusData,
    LuckyNumberCoordinator,
    MessagesCoordinator,
    ScheduleCoordinator,
    StudentInfoCoordinator,
    TimetableCoordinator,
    lucky_number,
)
from .services import async_setup_services
from .store import LibrusStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR, Platform.EVENT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions; they work for every loaded entry."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> bool:
    """Set up one student: storage, coordinators, platforms.

    The student info must load (it tells whether Librus is reachable). Its page
    also gives the first lucky number, so the lucky-number poll starts one interval
    later. The other data types load in the background: a slow or broken page does
    not block the setup, and its entities stay unavailable until their data arrives.
    """
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
    lucky = LuckyNumberCoordinator(hass, entry, api)
    lucky.async_set_updated_data(lucky_number(student.data.info))
    entry.runtime_data = LibrusData(
        api=api,
        store=store,
        student=student,
        lucky_number=lucky,
        messages=MessagesCoordinator(hass, entry, api, store),
        announcements=AnnouncementsCoordinator(hass, entry, api, store),
        grades=GradesCoordinator(hass, entry, api, store),
        schedule=ScheduleCoordinator(hass, entry, api, store),
        timetable=TimetableCoordinator(hass, entry, api),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    data = entry.runtime_data
    for coordinator in (
        data.messages,
        data.announcements,
        data.grades,
        data.schedule,
        data.timetable,
    ):
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), f"{coordinator.name} first refresh"
        )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> bool:
    """Bring the options of an older entry up to date.

    Minor version 2 (1.1.0): new options for the lucky number and the timetable
    with their defaults; the student-info interval moves to the new default only
    if it still holds the old one (D-114). Home Assistant itself refuses entries of a newer major
    version; a newer minor version loads unchanged.
    """
    if entry.minor_version < 2:
        options = {**entry.options}
        for key in NEW_OPTIONS_1_1:
            options.setdefault(key, DEFAULT_OPTIONS[key])
        if options.get(CONF_INTERVAL_STUDENT) == OLD_DEFAULT_INTERVAL_STUDENT:
            options[CONF_INTERVAL_STUDENT] = DEFAULT_OPTIONS[CONF_INTERVAL_STUDENT]
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
        _LOGGER.debug("Migrated entry %s to version 1.2", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> bool:
    """Unload the platforms, save the store and close the HTTP session."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.store.async_flush()
        await hass.async_add_executor_job(entry.runtime_data.api.close)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> None:
    """Delete the stored data of a removed entry."""
    await LibrusStore(hass, entry.entry_id).async_remove()
