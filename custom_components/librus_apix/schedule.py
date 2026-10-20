"""Schedule (terminarz) of one student: events by month, details, calendar data (F4, F5).

- The calendar of each month is one request; the detail page of an event is read
  only when the event is new or its list data changed (cached in the store).
- Lesson number -> start and end from the bell schedule (timetable); an hour ->
  one hour from it; neither -> an all-day event.
- The calendar description is readable lines, then one JSON line with all fields
  (D-018), so cards and automations can read it back with ``parse_description``.
- Triggers (F5, F17): the tracker scope of an event is its month, so months that
  a larger timeframe adds fire nothing.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import re
from typing import Any

from librus_apix.client import Client
from librus_apix.exceptions import DateError, ParseError
from librus_apix.schedule import Event, get_schedule, schedule_detail
from librus_apix.timetable import get_timetable

from .const import LIBRUS_TZ

_LOGGER = logging.getLogger(__name__)

# Marks our JSON line and its format version.
JSON_KEY = "librus_apix"
JSON_VERSION = 1
_HOUR = re.compile(r"(\d{1,2}):(\d{2})")
_UNKNOWN = "unknown"
# Lesson changes have no detail page, only a list text (I-004):
#   "Zastępstwo z <teacher> na lekcji nr: 5 (<subject>)"
#   "Odwołane zajęcia <br/><teacher> na lekcji nr: 5 (<subject>)": the part
#   before <br/> is the list subject, the rest the list title.
SUBSTITUTION = "Zastępstwo"
_LESSON_CHANGE = re.compile(
    rf"(?:(?P<kind>{SUBSTITUTION}) z )?(?P<teacher>.+?) na lekcji nr: ?\d+ \((?P<subject>.+)\)"
)
# Fields whose change fires changed_event ("date_added" and "details" do not).
SNAPSHOT_FIELDS = (
    "date",
    "lesson",
    "hour",
    "type",
    "subject",
    "teacher",
    "description",
)

type Bells = dict[int, tuple[str, str]]


@dataclass(frozen=True)
class ScheduleEvent:
    """One event of the schedule; ``detail`` comes from its detail page."""

    id: str
    day: date
    lesson: int | None
    hour: str | None
    list_subject: str
    list_title: str
    data: dict[str, str]
    detail: dict[str, str] = field(default_factory=dict)

    def _field(self, detail_key: str, data_key: str | None = None) -> str:
        value = self.detail.get(detail_key) or self.data.get(data_key or detail_key, "")
        return "" if value == _UNKNOWN else value.strip()

    def _change(self) -> tuple[str, str, str] | None:
        """(type, teacher, subject) of a substitution or cancelled lesson."""
        if "Rodzaj" in self.detail:
            return None
        match = _LESSON_CHANGE.fullmatch(self.list_title)
        if match is None:
            return None
        if match["kind"]:
            kind = match["kind"]
        elif self.list_subject and self.list_subject != self.list_title:
            kind = self.list_subject
        else:
            return None
        return kind, match["teacher"].strip(), match["subject"].strip()

    @property
    def type(self) -> str:
        """Event type, for example Sprawdzian, Wycieczka or Zastępstwo."""
        if change := self._change():
            return change[0]
        return self._field("Rodzaj") or self.list_title

    @property
    def subject(self) -> str:
        """Subject; empty for events without one."""
        if "Rodzaj" in self.detail:
            return self.detail.get("Przedmiot", "").strip()
        if change := self._change():
            return change[2]
        return self.list_subject if self.list_subject != self.list_title else ""

    @property
    def teacher(self) -> str:
        """Teacher who added the event; of a lesson change, the one Librus names (D-104)."""
        if teacher := self._field("Nauczyciel"):
            return teacher
        change = self._change()
        return change[1] if change else ""

    @property
    def description(self) -> str:
        """Description written by the teacher."""
        return self._field("Opis")

    @property
    def date_added(self) -> str:
        """When the event was added (Librus text)."""
        return self._field("Data dodania")

    @property
    def fingerprint(self) -> str:
        """Hash of the list data; another value means the event changed."""
        key = json.dumps(
            [
                self.day.isoformat(),
                self.lesson,
                self.hour,
                self.list_subject,
                self.list_title,
                self.data,
            ],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha1(key.encode()).hexdigest()[:16]


def months_in_range(today: date, timeframe: int) -> list[tuple[int, int]]:
    """Return (year, month) of the current month and ``timeframe`` months after."""
    months = []
    year, month = today.year, today.month
    for _ in range(timeframe + 1):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _event_id(event: Event, day: date) -> str:
    """Librus link of the event (prefix/id); without one, a hash of its data."""
    if event.href:
        return event.href
    key = f"{day.isoformat()}|{event.subject}|{event.title}|{event.number}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _list_event(event: Event, year: int, month: int, day: int) -> ScheduleEvent:
    when = date(year, month, day)
    hour = event.hour.strip() if event.hour and event.hour != _UNKNOWN else None
    return ScheduleEvent(
        id=_event_id(event, when),
        day=when,
        lesson=event.number if isinstance(event.number, int) else None,
        hour=hour,
        list_subject=event.subject.strip(),
        list_title=event.title.strip(),
        data={k: v for k, v in event.data.items() if v and v != _UNKNOWN},
    )


def read_months(client: Client, months: list[tuple[int, int]]) -> list[ScheduleEvent]:
    """Read the calendar of each month (runs in the executor)."""
    events = []
    for year, month in months:
        for day, items in get_schedule(client, str(month), str(year)).items():
            events.extend(_list_event(item, year, month, int(day)) for item in items)
    return sorted(events, key=lambda e: (e.day, e.lesson or 0, e.id))


def read_details(client: Client, event_ids: list[str]) -> dict[str, dict[str, str]]:
    """Read the detail page of each event (executor); a broken page gives {}."""
    details = {}
    for event_id in event_ids:
        prefix, _, number = event_id.partition("/")
        try:
            details[event_id] = schedule_detail(client, prefix, number)
        except ParseError:
            _LOGGER.debug("No details for schedule event %s", event_id)
            details[event_id] = {}
    return details


def read_bells(client: Client, today: date) -> Bells:
    """Return lesson number -> (start, end) from the timetable of this week."""
    monday = today - timedelta(days=today.weekday())
    try:
        week = get_timetable(client, monday)
    except (ParseError, DateError, IndexError, ValueError) as err:
        _LOGGER.debug("No bell schedule from the timetable: %s", err)
        return {}
    return {
        period.number: (period.date_from, period.date_to)
        for day in week
        for period in day
        if period.date_from and period.date_to
    }


def local_time(day: date, clock: str) -> datetime | None:
    """Polish time of ``clock`` ("8:55", "08:55") on ``day``; None if not a time."""
    match = _HOUR.fullmatch(clock.strip())
    if match is None:
        return None
    return datetime(
        day.year, day.month, day.day, int(match[1]), int(match[2]), tzinfo=LIBRUS_TZ
    )


def event_times(
    event: ScheduleEvent, bells: Bells
) -> tuple[date | datetime, date | datetime]:
    """Return (start, end): lesson times, one hour from the hour, or all day."""
    if event.lesson is not None and event.lesson in bells:
        start, end = (local_time(event.day, clock) for clock in bells[event.lesson])
        if start and end:
            return start, end
    if event.hour and (start := local_time(event.day, event.hour)):
        return start, start + timedelta(hours=1)
    return event.day, event.day + timedelta(days=1)


def summary(event: ScheduleEvent) -> str:
    """Calendar title: type and subject (or the description without a subject)."""
    if event.subject:
        return f"{event.type}: {event.subject}"
    if event.description and event.description != event.type:
        return f"{event.type}: {event.description}"
    return event.type


def event_fields(event: ScheduleEvent) -> dict[str, Any]:
    """All fields of an event (JSON line, event triggers)."""
    return {
        "id": event.id,
        "date": event.day.isoformat(),
        "type": event.type,
        "subject": event.subject,
        "teacher": event.teacher,
        "lesson": event.lesson,
        "hour": event.hour,
        "description": event.description,
        "date_added": event.date_added,
        "details": event.detail,
    }


def month_scope(day: date) -> str:
    """Tracker scope of an event: its month, "2026-10"."""
    return f"{day.year:04d}-{day.month:02d}"


def snapshot(event: ScheduleEvent) -> dict[str, Any]:
    """Values compared between polls; another value fires changed_event."""
    fields = event_fields(event)
    return {key: fields[key] for key in SNAPSHOT_FIELDS}


def trigger_details(event: ScheduleEvent, bells: Bells) -> dict[str, Any]:
    """Event data of a trigger: all fields, the title and the calendar times."""
    start, end = event_times(event, bells)
    return {
        **event_fields(event),
        "summary": summary(event),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "all_day": not isinstance(start, datetime),
    }


def describe(event: ScheduleEvent) -> str:
    """Readable lines, then one JSON line with all fields (D-018)."""
    lines = [f"{key}: {value}" for key, value in event.detail.items() if value]
    if not lines:
        lines = [f"Rodzaj: {event.type}"]
        lines += [f"{key}: {value}" for key, value in event.data.items()]
        if event.subject:
            lines.append(f"Przedmiot: {event.subject}")
        if event.teacher and "Nauczyciel" not in event.data:
            lines.append(f"Nauczyciel: {event.teacher}")
    payload = {JSON_KEY: JSON_VERSION, **event_fields(event)}
    lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def parse_description(text: str) -> dict[str, Any] | None:
    """Return the fields from the JSON line of a calendar description."""
    for line in reversed(text.splitlines()):
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except ValueError:
                return None
            if isinstance(payload, dict) and payload.pop(JSON_KEY, None) is not None:
                return payload
            return None
    return None
