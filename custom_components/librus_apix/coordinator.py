"""Data update coordinators: one per data type and entry, each with its own interval."""

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from librus_apix.student_information import StudentInformation, get_student_information

from .api import LibrusApi
from .const import CONF_INTERVAL_STUDENT, DEFAULT_OPTIONS, DOMAIN
from .exceptions import LibrusAuthError, LibrusError, LibrusUnavailableError
from .store import LibrusStore

_LOGGER = logging.getLogger(__name__)


@dataclass
class LibrusData:
    """Runtime data of one entry (one student)."""

    api: LibrusApi
    store: LibrusStore
    student: StudentInfoCoordinator


type LibrusConfigEntry = ConfigEntry[LibrusData]


class LibrusCoordinator[T](DataUpdateCoordinator[T]):
    """Base coordinator: interval from the options, Librus errors mapped for HA."""

    config_entry: LibrusConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: LibrusConfigEntry,
        api: LibrusApi,
        data_type: str,
        interval_option: str,
    ) -> None:
        """Create the coordinator for one data type of the entry."""
        minutes = entry.options.get(interval_option, DEFAULT_OPTIONS[interval_option])
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {data_type}",
            update_interval=timedelta(minutes=minutes),
            always_update=False,
        )
        self.api = api

    async def _async_update_data(self) -> T:
        """Fetch the data; a rejected login starts the reauth flow."""
        try:
            return await self._async_fetch()
        except LibrusAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except LibrusUnavailableError as err:
            # A backoff shorter than the interval must not make polling faster.
            interval = (
                self.update_interval.total_seconds() if self.update_interval else 0
            )
            retry_after = err.retry_after if (err.retry_after or 0) > interval else None
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="maintenance" if err.maintenance else "unavailable",
                retry_after=retry_after,
            ) from err
        except LibrusError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _async_fetch(self) -> T:
        """Read the data from Librus (subclasses)."""
        raise NotImplementedError


class StudentInfoCoordinator(LibrusCoordinator[StudentInformation]):
    """Student information and lucky number (one page)."""

    def __init__(
        self, hass: HomeAssistant, entry: LibrusConfigEntry, api: LibrusApi
    ) -> None:
        """Use the student-info interval."""
        super().__init__(hass, entry, api, "student info", CONF_INTERVAL_STUDENT)

    async def _async_fetch(self) -> StudentInformation:
        return await self.api.async_call(get_student_information)
