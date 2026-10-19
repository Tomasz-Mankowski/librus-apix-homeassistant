"""Sensors of a student: information fields and lucky number (F3)."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from librus_apix.student_information import StudentInformation

from .coordinator import LibrusConfigEntry, StudentInfoCoordinator
from .entity import LibrusEntity

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
    """Add the student sensors."""
    coordinator = entry.runtime_data.student
    async_add_entities(StudentSensor(coordinator, desc) for desc in STUDENT_SENSORS)


class StudentSensor(LibrusEntity[StudentInfoCoordinator], SensorEntity):
    """One field of the student information."""

    entity_description: StudentSensorDescription

    @property
    def native_value(self) -> StateType:
        """Return the field value."""
        return self.entity_description.value_fn(self.coordinator.data)
