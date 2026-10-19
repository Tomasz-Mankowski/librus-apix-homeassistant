"""Schedule calendar of a student (F5): Librus events with real lesson times."""

from datetime import date, datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import LIBRUS_TZ
from .coordinator import LibrusConfigEntry, ScheduleCoordinator
from .entity import LibrusEntity
from .schedule import describe, event_times, summary

# Coordinators fetch the data; entities never poll.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LibrusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the schedule calendar."""
    async_add_entities([ScheduleCalendar(entry.runtime_data.schedule)])


def _as_datetime(value: date | datetime) -> datetime:
    """Start of the day in Polish time for all-day events."""
    if isinstance(value, datetime):
        return value
    return datetime(value.year, value.month, value.day, tzinfo=LIBRUS_TZ)


class ScheduleCalendar(LibrusEntity[ScheduleCoordinator], CalendarEntity):
    """Events of the current month and the next N months."""

    # Newer releases read the color from a CalendarEntityDescription; set it here
    # so a plain EntityDescription works on every supported version.
    _attr_initial_color = None

    def __init__(self, coordinator: ScheduleCoordinator) -> None:
        """Create the schedule calendar."""
        super().__init__(
            coordinator, EntityDescription(key="schedule", translation_key="schedule")
        )

    def _events(self) -> list[CalendarEvent]:
        if self.coordinator.data is None:
            # Added before the first schedule poll has finished.
            return []
        student = self.coordinator.config_entry.runtime_data.student.data
        bells = student.bells if student else {}
        events = []
        for event in self.coordinator.data.events:
            start, end = event_times(event, bells)
            events.append(
                CalendarEvent(
                    start=start,
                    end=end,
                    summary=summary(event),
                    description=describe(event),
                    uid=event.id,
                )
            )
        return sorted(events, key=lambda e: _as_datetime(e.start))

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
