"""Event entities: one per data type and student; one event per new or changed item.

Several new items in one poll fire several events, one state write each, so an
automation in queued mode handles every one (F16). Every event carries the student
name and the config entry id (F1).
"""

from collections.abc import Iterable
from typing import Any

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import (
    AnnouncementsCoordinator,
    AnnouncementsData,
    GradesCoordinator,
    LibrusConfigEntry,
    LibrusCoordinator,
    MessagesCoordinator,
    MessagesData,
    announcement_details,
    message_details,
)
from .entity import LibrusEntity
from .grades import GradesPage, final_details, grade_details

ATTR_STUDENT = "student"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

EVENT_NEW_ANNOUNCEMENT = "new_announcement"
EVENT_NEW_MESSAGE = "new_message"
EVENT_NEW_GRADE = "new_grade"
EVENT_GRADE_CHANGED = "grade_changed"
EVENT_FINAL_GRADE = "final_grade"

# Coordinators fetch the data; entities never poll.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LibrusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the event entities of the student."""
    data = entry.runtime_data
    async_add_entities(
        [
            MessagesEvent(data.messages),
            AnnouncementsEvent(data.announcements),
            GradesEvent(data.grades),
        ]
    )


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


class MessagesEvent(LibrusEventEntity[MessagesCoordinator]):
    """new_message for each new received message (details, no body)."""

    def __init__(self, coordinator: MessagesCoordinator) -> None:
        """Create the messages event entity."""
        super().__init__(
            coordinator,
            EventEntityDescription(
                key="messages",
                translation_key="messages",
                event_types=[EVENT_NEW_MESSAGE],
            ),
        )

    def _events(self, data: MessagesData) -> Iterable[tuple[str, dict[str, Any]]]:
        return [
            (EVENT_NEW_MESSAGE, message_details(change.item))
            for change in data.changes
            if change.kind == "new"
        ]


class AnnouncementsEvent(LibrusEventEntity[AnnouncementsCoordinator]):
    """new_announcement for each new announcement, with the full text."""

    # The text can be long: keep it out of the recorder.
    _unrecorded_attributes = frozenset({"content"})

    def __init__(self, coordinator: AnnouncementsCoordinator) -> None:
        """Create the announcements event entity."""
        super().__init__(
            coordinator,
            EventEntityDescription(
                key="announcements",
                translation_key="announcements",
                event_types=[EVENT_NEW_ANNOUNCEMENT],
            ),
        )

    def _events(self, data: AnnouncementsData) -> Iterable[tuple[str, dict[str, Any]]]:
        return [
            (EVENT_NEW_ANNOUNCEMENT, announcement_details(change.item))
            for change in data.changes
            if change.kind == "new"
        ]


class GradesEvent(LibrusEventEntity[GradesCoordinator]):
    """new_grade, grade_changed and final_grade for each change of a poll.

    A correction is a new_grade with ``is_correction`` and the ``original_grade``.
    """

    def __init__(self, coordinator: GradesCoordinator) -> None:
        """Create the grades event entity."""
        super().__init__(
            coordinator,
            EventEntityDescription(
                key="grades",
                translation_key="grades",
                event_types=[EVENT_NEW_GRADE, EVENT_GRADE_CHANGED, EVENT_FINAL_GRADE],
            ),
        )

    def _events(self, data: GradesPage) -> Iterable[tuple[str, dict[str, Any]]]:
        rules = self.coordinator.rules
        for change in data.grade_changes:
            item = change.item
            details = {
                **grade_details(item.grade, rules),
                "subject": item.subject,
                "semester": item.semester,
            }
            if change.kind == "new":
                original = item.original
                yield (
                    EVENT_NEW_GRADE,
                    {
                        **details,
                        "is_correction": original is not None,
                        "original_grade": (
                            grade_details(original, rules) if original else None
                        ),
                    },
                )
            else:
                old = change.old["grade"] if change.old else None
                yield EVENT_GRADE_CHANGED, {**details, "old_grade": old}
        for change in data.final_changes:
            yield (
                EVENT_FINAL_GRADE,
                {
                    **final_details(change.item.final),
                    "subject": change.item.subject,
                    "old_grade": change.old["grade"] if change.old else None,
                },
            )
