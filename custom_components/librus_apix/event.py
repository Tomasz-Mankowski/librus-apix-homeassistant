"""Event entities: one per data type and student; one event per new or changed item.

Several new items in one poll fire several events, one state write each, so an
automation in queued mode handles every one (F16). Every event carries the student
name and the config entry id (F1).
"""

from collections.abc import Iterable
from typing import Any

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import callback

from .coordinator import LibrusCoordinator
from .entity import LibrusEntity

ATTR_STUDENT = "student"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

# Coordinators fetch the data; entities never poll.
PARALLEL_UPDATES = 0


class LibrusEventEntity[C: LibrusCoordinator[Any]](LibrusEntity[C], EventEntity):
    """Fires the events of each new coordinator result once."""

    def __init__(self, coordinator: C, description: EventEntityDescription) -> None:
        """Start with no handled result."""
        super().__init__(coordinator, description)
        self._handled: object = None

    async def async_added_to_hass(self) -> None:
        """Also fire the events of the first poll (items new since the last run)."""
        await super().async_added_to_hass()
        self._fire_events()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire the events of a new result, then update the state."""
        self._fire_events()
        super()._handle_coordinator_update()

    @callback
    def _fire_events(self) -> None:
        data = self.coordinator.data
        if data is None or data is self._handled:
            return
        self._handled = data
        entry = self.coordinator.config_entry
        for event_type, event_data in self._events(data):
            self._trigger_event(
                event_type,
                {
                    **event_data,
                    ATTR_STUDENT: entry.title,
                    ATTR_CONFIG_ENTRY_ID: entry.entry_id,
                },
            )
            self.async_write_ha_state()

    def _events(self, data: Any) -> Iterable[tuple[str, dict[str, Any]]]:
        """Return (event type, event data) for each new or changed item."""
        raise NotImplementedError
