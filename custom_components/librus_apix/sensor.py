"""Sensors of a student: information (F3), messages (F7), announcements (F9),
grades per subject (F11)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import slugify

from librus_apix.student_information import StudentInformation

from .coordinator import (
    AnnouncementsCoordinator,
    GradesCoordinator,
    LibrusConfigEntry,
    MessagesCoordinator,
    StudentInfoCoordinator,
    announcement_details,
    message_details,
)
from .entity import LibrusEntity
from .grades import (
    PERIODS,
    SubjectGrades,
    descriptive_details,
    final_details,
    grade_details,
    period_average,
)

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
    """Add the sensors; grade sensors for each subject, also for new subjects.

    A descriptive-grade sensor is added only for a subject that has such grades.
    """
    data = entry.runtime_data
    async_add_entities(
        [
            *(StudentSensor(data.student, desc) for desc in STUDENT_SENSORS),
            MessagesSensor(data.messages),
            AnnouncementsSensor(data.announcements),
        ]
    )

    known: set[str] = set()
    known_descriptive: set[str] = set()

    @callback
    def _add_subjects() -> None:
        if (page := data.grades.data) is None:
            return
        new = [name for name in page.subjects if name not in known]
        known.update(new)
        new_descriptive = [
            name
            for name in page.descriptive_subjects()
            if name not in known_descriptive
        ]
        known_descriptive.update(new_descriptive)
        async_add_entities(
            [
                *(SubjectSensor(data.grades, name) for name in new),
                *(DescriptiveSensor(data.grades, name) for name in new_descriptive),
            ]
        )

    _add_subjects()
    entry.async_on_unload(data.grades.async_add_listener(_add_subjects))


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


class SubjectSensor(LibrusEntity[GradesCoordinator], SensorEntity):
    """Average of the current semester of one subject; all its grades as attributes.

    The average is the one Librus shows, or the calculated one when Librus shows
    none (``average_source``). Semester and year grades are kept apart.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    # Grade lists can be long: keep them out of the recorder (16 KB attribute limit).
    _unrecorded_attributes = frozenset({"grades", "final_grades"})

    def __init__(self, coordinator: GradesCoordinator, subject: str) -> None:
        """Create the sensor of ``subject``; the name is the subject name."""
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key=f"grades_{slugify(subject)}", translation_key="subject_grades"
            ),
        )
        self._subject = subject
        self._attr_translation_placeholders = {"subject": subject}

    @property
    def available(self) -> bool:
        """Available while the subject is on the grades page."""
        return super().available and self._subject in self.coordinator.data.subjects

    @property
    def _grades(self) -> SubjectGrades:
        return self.coordinator.data.subjects[self._subject]

    @property
    def _current_period(self) -> str:
        return PERIODS[self.coordinator.data.semester - 1]

    @property
    def native_value(self) -> float | None:
        """Return the average of the current semester."""
        return period_average(
            self._grades, self._current_period, self.coordinator.rules
        )[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the averages, the grades by semester and the final grades."""
        rules = self.coordinator.rules
        subject = self._grades
        averages = {}
        for period in PERIODS:
            value, _ = period_average(subject, period, rules)
            averages[period] = round(value, 2) if value is not None else None
        return {
            "subject": subject.name,
            "semester": self.coordinator.data.semester,
            "average_source": period_average(subject, self._current_period, rules)[1],
            "averages": averages,
            "grades": {
                period: [grade_details(g, rules) for g in subject.grades[number]]
                for number, period in ((1, PERIODS[0]), (2, PERIODS[1]))
            },
            "final_grades": [final_details(f) for f in subject.finals],
        }


class DescriptiveSensor(LibrusEntity[GradesCoordinator], SensorEntity):
    """Number of descriptive grades of one subject; the grades as an attribute."""

    # The texts can be long: keep them out of the recorder (16 KB attribute limit).
    _unrecorded_attributes = frozenset({"grades"})

    def __init__(self, coordinator: GradesCoordinator, subject: str) -> None:
        """Create the descriptive-grade sensor of ``subject``."""
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key=f"descriptive_{slugify(subject)}",
                translation_key="subject_descriptive",
            ),
        )
        self._subject = subject
        self._attr_translation_placeholders = {"subject": subject}

    @property
    def native_value(self) -> int:
        """Return the number of descriptive grades."""
        return len(self.coordinator.data.descriptive_subjects().get(self._subject, []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the descriptive grades by semester."""
        items = self.coordinator.data.descriptive_subjects().get(self._subject, [])
        return {
            "subject": self._subject,
            "grades": {
                period: [descriptive_details(i) for i in items if i.semester == number]
                for number, period in ((1, PERIODS[0]), (2, PERIODS[1]))
            },
        }
