"""Data update coordinators: one per data type and entry, each with its own interval."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from librus_apix.announcements import Announcement, get_announcements
from librus_apix.client import Client
from librus_apix.exceptions import ParseError
from librus_apix.messages import Message, get_received, parse, unwrap_message_data
from librus_apix.student_information import StudentInformation, get_student_information

from .api import LibrusApi
from .average import AverageRules
from .const import (
    CONF_INTERVAL_ANNOUNCEMENTS,
    CONF_INTERVAL_GRADES,
    CONF_INTERVAL_MESSAGES,
    CONF_INTERVAL_STUDENT,
    CONF_MESSAGE_COUNT,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .exceptions import LibrusAuthError, LibrusError, LibrusUnavailableError
from .grades import GradesPage, read_grades
from .store import LibrusStore
from .tracker import Change, TrackedItem, Tracker

_LOGGER = logging.getLogger(__name__)

# Librus shows Polish local time.
LIBRUS_TZ = ZoneInfo("Europe/Warsaw")

# Store key of the cached message contents.
STORE_BODIES = "message_bodies"


@dataclass
class LibrusData:
    """Runtime data of one entry (one student)."""

    api: LibrusApi
    store: LibrusStore
    student: StudentInfoCoordinator
    messages: MessagesCoordinator
    announcements: AnnouncementsCoordinator
    grades: GradesCoordinator


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


def read_message_content(client: Client, msg_id: str) -> dict[str, Any]:
    """Read one message page: author, title, date, body and attachment names.

    One request; the library's message_content gives no attachment names.
    """
    soup = BeautifulSoup(client.get(f"{client.MESSAGE_URL}/{msg_id}").text, "lxml")
    table = soup.select_one("table[class='stretch']")
    rows = table.select("tr") if table else []
    body = soup.find("div", attrs={"class": "container-message-content"})
    if len(rows) < 3 or body is None:
        raise ParseError("Error in parsing message content.")
    author, title, date = (unwrap_message_data(row).strip() for row in rows[:3])
    attachments = [
        cell.text.replace("\xa0", " ").strip()
        for cell in soup.select("td")
        if cell.select_one("img[src*='filetype_icons']")
    ]
    return {
        "author": author,
        "title": title,
        "date": librus_datetime(date),
        "content": body.text.strip(),
        "attachments": attachments,
    }


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
        self._store = store
        self._tracker: Tracker[Message] = Tracker(store, "messages")

    @property
    def bodies(self) -> dict[str, dict[str, Any]]:
        """Message contents read so far, by message id (kept in the store)."""
        return self._store.data.setdefault(STORE_BODIES, {})

    async def _async_fetch(self) -> MessagesData:
        messages = await self.api.async_call(read_messages, self._count)
        # Oldest first, so the events of one poll come in time order.
        changes = self._tracker.update(
            TrackedItem(message_id(m), {}, m) for m in reversed(messages)
        )
        listed = {message_id(m) for m in messages}
        bodies = self.bodies
        if unlisted := bodies.keys() - listed:
            for key in unlisted:
                del bodies[key]
            self._store.async_schedule_save()
        return MessagesData(messages, changes)

    async def async_get_content(self, msg_id: str) -> dict[str, Any]:
        """Return the content of a listed message; read it from Librus only once.

        Reading a body marks the message read in Librus, so it is marked read here
        too. Raises KeyError for a message that is not on the list.
        """
        listed = self.data.messages if self.data else []
        message = next((m for m in listed if message_id(m) == msg_id), None)
        if message is None:
            raise KeyError(msg_id)
        if msg_id not in self.bodies:
            self.bodies[msg_id] = await self.api.async_call(
                read_message_content, msg_id
            )
            self._store.async_schedule_save()
            message.unread = False
            self.async_update_listeners()
        return {"id": msg_id, **self.bodies[msg_id]}


def announcement_id(item: Announcement) -> str:
    """Stable id of an announcement: the library gives none (D-029)."""
    key = f"{item.title.strip()}|{item.author.strip()}|{item.date.strip()}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def announcement_details(item: Announcement) -> dict[str, Any]:
    """All details of an announcement, with the full text."""
    return {
        "id": announcement_id(item),
        "title": item.title.strip(),
        "author": item.author.strip(),
        "date": item.date.strip(),
        "content": item.description.strip(),
    }


@dataclass
class AnnouncementsData:
    """All announcements and the new ones of this poll."""

    announcements: list[Announcement]
    changes: list[Change[Announcement]]


class AnnouncementsCoordinator(LibrusCoordinator[AnnouncementsData]):
    """All announcements with the full text (Librus has no read state for them)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: LibrusConfigEntry,
        api: LibrusApi,
        store: LibrusStore,
    ) -> None:
        """Use the announcements interval."""
        super().__init__(hass, entry, api, "announcements", CONF_INTERVAL_ANNOUNCEMENTS)
        self._tracker: Tracker[Announcement] = Tracker(store, "announcements")

    async def _async_fetch(self) -> AnnouncementsData:
        announcements = await self.api.async_call(get_announcements)
        # Librus lists the newest first; events go oldest first.
        changes = self._tracker.update(
            TrackedItem(announcement_id(a), {}, a) for a in reversed(announcements)
        )
        return AnnouncementsData(announcements, changes)


class GradesCoordinator(LibrusCoordinator[GradesPage]):
    """Grades, semester/final grades and averages (one page per poll)."""

    def __init__(
        self, hass: HomeAssistant, entry: LibrusConfigEntry, api: LibrusApi
    ) -> None:
        """Use the grades interval and the average rules."""
        super().__init__(hass, entry, api, "grades", CONF_INTERVAL_GRADES)
        self.rules = AverageRules()

    async def _async_fetch(self) -> GradesPage:
        return await self.api.async_call(read_grades)
