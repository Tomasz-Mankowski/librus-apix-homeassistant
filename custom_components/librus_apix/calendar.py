"""Calendars of a student: the schedule (F5) and the timetable (F3), with real times."""

from datetime import date, datetime
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import schedule, timetable
from .const import LIBRUS_TZ
from .coordinator import (
    LibrusConfigEntry,
    LibrusCoordinator,
    ScheduleCoordinator,
    TimetableCoordinator,
)
from .entity import LibrusEntity

# Coordinators fetch the data; entities never poll.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LibrusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the schedule and timetable calendars."""
    data = entry.runtime_data
    async_add_entities(
        [ScheduleCalendar(data.schedule), TimetableCalendar(data.timetable)]
    )


def _as_datetime(value: date | datetime) -> datetime:
    """Start of the day in Polish time for all-day events."""
    if isinstance(value, datetime):
        return value
    return datetime(value.year, value.month, value.day, tzinfo=LIBRUS_TZ)


class LibrusCalendar[C: LibrusCoordinator[Any]](LibrusEntity[C], CalendarEntity):
    """Calendar of the events a coordinator holds (``_events``)."""

    # Newer releases read the color from a CalendarEntityDescription; set it here
    # so a plain EntityDescription works on every supported version.
    _attr_initial_color = None

    def __init__(self, coordinator: C, key: str) -> None:
        """Create the calendar; ``key`` is also its translation key."""
        super().__init__(coordinator, EntityDescription(key=key, translation_key=key))

    def _events(self) -> list[CalendarEvent]:
        """All events, sorted by start; empty before the first poll."""
        raise NotImplementedError

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next event."""
        now = dt_util.now()
        return next((e for e in self._events() if _as_datetime(e.end) > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the events between start_date and end_date."""
        return [
            event
            for event in self._events()
            if _as_datetime(event.end) > start_date
            and _as_datetime(event.start) < end_date
        ]


class ScheduleCalendar(LibrusCalendar[ScheduleCoordinator]):
    """Events of the current month and the next N months."""

    def __init__(self, coordinator: ScheduleCoordinator) -> None:
        """Create the schedule calendar."""
        super().__init__(coordinator, "schedule")

    def _events(self) -> list[CalendarEvent]:
        if self.coordinator.data is None:
            # Added before the first schedule poll has finished.
            return []
        bells = self.coordinator.bells
        events = []
        for event in self.coordinator.data.events:
            start, end = schedule.event_times(event, bells)
            events.append(
                CalendarEvent(
                    start=start,
                    end=end,
                    summary=schedule.summary(event),
                    description=schedule.describe(event),
                    uid=event.id,
                )
            )
        return sorted(events, key=lambda e: _as_datetime(e.start))


class TimetableCalendar(LibrusCalendar[TimetableCoordinator]):
    """Lessons of the current week and the next N weeks (F3)."""

    def __init__(self, coordinator: TimetableCoordinator) -> None:
        """Create the timetable calendar."""
        super().__init__(coordinator, "timetable")

    def _events(self) -> list[CalendarEvent]:
        if self.coordinator.data is None:
            # Added before the first timetable poll has finished.
            return []
        events = []
        for lesson in self.coordinator.data.lessons:
            start, end = timetable.lesson_times(lesson)
            events.append(
                CalendarEvent(
                    start=start,
                    end=end,
                    summary=timetable.summary(lesson),
                    description=timetable.describe(lesson),
                    location=lesson.classroom or None,
                    uid=lesson.id,
                )
            )
        return sorted(events, key=lambda e: _as_datetime(e.start))
