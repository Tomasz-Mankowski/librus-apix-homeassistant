"""Data update coordinators: one per data type and entry, each with its own interval."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from librus_apix.client import Client
from librus_apix.messages import Message, get_received, parse
from librus_apix.student_information import StudentInformation, get_student_information

from .api import LibrusApi
from .const import (
    CONF_INTERVAL_MESSAGES,
    CONF_INTERVAL_STUDENT,
    CONF_MESSAGE_COUNT,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .exceptions import LibrusAuthError, LibrusError, LibrusUnavailableError
from .store import LibrusStore
from .tracker import Change, TrackedItem, Tracker

_LOGGER = logging.getLogger(__name__)

# Librus shows Polish local time.
LIBRUS_TZ = ZoneInfo("Europe/Warsaw")


@dataclass
class LibrusData:
    """Runtime data of one entry (one student)."""

    api: LibrusApi
    store: LibrusStore
    student: StudentInfoCoordinator
    messages: MessagesCoordinator


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


def librus_datetime(text: str) -> str:
    """Return a Librus time ("2026-10-18 08:15:02", Polish time) as ISO 8601."""
    try:
        parsed = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return text.strip()
    return parsed.replace(tzinfo=LIBRUS_TZ).isoformat()


def message_id(message: Message) -> str:
    """Librus id of a message (from its link), or author|title|date without one."""
    return message.href or f"{message.author}|{message.title}|{message.date}"


def message_details(message: Message) -> dict[str, Any]:
    """Details of a message for attributes and events (no body)."""
    return {
        "id": message_id(message),
        "author": message.author.strip(),
        "title": message.title.strip(),
        "date": librus_datetime(message.date),
        "unread": message.unread,
        "has_attachment": message.has_attachment,
    }


_PAGE_COUNT = re.compile(r"z(\d+)")


def read_messages(client: Client, count: int) -> list[Message]:
    """Return the last ``count`` received messages, newest first.

    Page 0 comes with a GET, which also shows the page count; more pages are read
    only while fewer than ``count`` messages are known. Bodies are never read.
    """
    soup = BeautifulSoup(client.get(client.MESSAGE_URL).text, "lxml")
    messages = parse(soup)
    pages = 1
    if (pagination := soup.select_one("div.pagination > span")) and (
        match := _PAGE_COUNT.search(pagination.text.replace("\xa0", ""))
    ):
        pages = int(match[1])
    page = 1
    while len(messages) < count and page < pages:
        messages += get_received(client, page)
        page += 1
    return messages[:count]


@dataclass
class MessagesData:
    """Last N received messages and the new ones of this poll."""

    messages: list[Message]
    changes: list[Change[Message]]


class MessagesCoordinator(LibrusCoordinator[MessagesData]):
    """Received messages (list pages only, no bodies)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: LibrusConfigEntry,
        api: LibrusApi,
        store: LibrusStore,
    ) -> None:
        """Use the messages interval and the message count option."""
        super().__init__(hass, entry, api, "messages", CONF_INTERVAL_MESSAGES)
        self._count = entry.options.get(
            CONF_MESSAGE_COUNT, DEFAULT_OPTIONS[CONF_MESSAGE_COUNT]
        )
        self._tracker: Tracker[Message] = Tracker(store, "messages")

    async def _async_fetch(self) -> MessagesData:
        messages = await self.api.async_call(read_messages, self._count)
        # Oldest first, so the events of one poll come in time order.
        changes = self._tracker.update(
            TrackedItem(message_id(m), {}, m) for m in reversed(messages)
        )
        return MessagesData(messages, changes)
