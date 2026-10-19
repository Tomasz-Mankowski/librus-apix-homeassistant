"""Sensors of a student: information fields and lucky number (F3)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from librus_apix.student_information import StudentInformation

from .coordinator import (
    AnnouncementsCoordinator,
    LibrusConfigEntry,
    MessagesCoordinator,
    StudentInfoCoordinator,
    announcement_details,
    message_details,
)
from .entity import LibrusEntity

ATTR_ANNOUNCEMENTS = "announcements"
ATTR_MESSAGES = "messages"

# Coordinators fetch the data; entities never poll.
PARALLEL_UPDATES = 0

MAX_STATE_LENGTH = 255


@dataclass(frozen=True, kw_only=True)
class StudentSensorDescription(SensorEntityDescription):
    """Sensor reading one field of the student information."""

    value_fn: Callable[[StudentInformation], StateType]


STUDENT_SENSORS = (
    StudentSensorDescription(
        key="student", translation_key="student", value_fn=lambda info: info.name
    ),
    StudentSensorDescription(
        key="class_name",
        translation_key="class_name",
        value_fn=lambda info: info.class_name,
    ),
    StudentSensorDescription(
        key="tutor", translation_key="tutor", value_fn=lambda info: info.tutor
    ),
    StudentSensorDescription(
        key="school",
        translation_key="school",
        value_fn=lambda info: info.school[:MAX_STATE_LENGTH],
    ),
    StudentSensorDescription(
        key="student_number",
        translation_key="student_number",
        value_fn=lambda info: info.number,
    ),
    StudentSensorDescription(
        key="lucky_number",
        translation_key="lucky_number",
        # The library returns "?" when Librus shows no lucky number.
        value_fn=lambda info: (
            info.lucky_number if isinstance(info.lucky_number, int) else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LibrusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the student and messages sensors."""
    data = entry.runtime_data
    async_add_entities(
        [
            *(StudentSensor(data.student, desc) for desc in STUDENT_SENSORS),
            MessagesSensor(data.messages),
            AnnouncementsSensor(data.announcements),
        ]
    )


class StudentSensor(LibrusEntity[StudentInfoCoordinator], SensorEntity):
    """One field of the student information."""

    entity_description: StudentSensorDescription

    @property
    def native_value(self) -> StateType:
        """Return the field value."""
        return self.entity_description.value_fn(self.coordinator.data)


class MessagesSensor(LibrusEntity[MessagesCoordinator], SensorEntity):
    """Unread message count; the last N messages (no bodies) as an attribute."""

    # The list can be large: keep it out of the recorder (16 KB attribute limit).
    _unrecorded_attributes = frozenset({ATTR_MESSAGES})

    def __init__(self, coordinator: MessagesCoordinator) -> None:
        """Create the messages sensor."""
        super().__init__(
            coordinator,
            SensorEntityDescription(key="messages", translation_key="messages"),
        )

    @property
    def native_value(self) -> int:
        """Return the number of unread messages."""
        return sum(message.unread for message in self.coordinator.data.messages)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the message list; content_cached tells if the body was read."""
        bodies = self.coordinator.bodies
        return {
            ATTR_MESSAGES: [
                {**details, "content_cached": details["id"] in bodies}
                for details in map(message_details, self.coordinator.data.messages)
            ]
        }


class AnnouncementsSensor(LibrusEntity[AnnouncementsCoordinator], SensorEntity):
    """Number of announcements; all of them with the full text as an attribute."""

    # The texts can be long: keep them out of the recorder (16 KB attribute limit).
    _unrecorded_attributes = frozenset({ATTR_ANNOUNCEMENTS})

    def __init__(self, coordinator: AnnouncementsCoordinator) -> None:
        """Create the announcements sensor."""
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="announcements", translation_key="announcements"
            ),
        )

    @property
    def native_value(self) -> int:
        """Return the number of announcements."""
        return len(self.coordinator.data.announcements)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all announcements."""
        return {
            ATTR_ANNOUNCEMENTS: [
                announcement_details(a) for a in self.coordinator.data.announcements
            ]
        }
