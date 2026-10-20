"""Timetable (plan lekcji) of one student: lessons of the current and next weeks (F3).

- Librus serves one week per request; the timetable covers the current week and
  the next N weeks (option ``timetable_weeks``, D-112).
- One record per lesson: date, lesson number, times, subject, teacher, classroom
  and the changes Librus shows on it (substitution, cancellation, ...) with the
  details of their tooltip. Empty periods give no record.
- No triggers (D-113): lesson changes fire through the schedule.
"""

from dataclasses import dataclass
from datetime import date, timedelta
import logging
import re

from librus_apix.client import Client
from librus_apix.exceptions import DateError, ParseError
from librus_apix.timetable import Period, get_timetable

from .exceptions import LibrusParseError

_LOGGER = logging.getLogger(__name__)

# "Adam Rachunek s. 12": teacher, then the classroom after "s." (sala).
_TEACHER_CLASSROOM = re.compile(r"(?:(?P<teacher>.*?)\s+)?s\.\s*(?P<classroom>.+)")
# Notice of a cancelled lesson: "odwołane" (the lesson stays, struck through).
_CANCELLED = "odwołan"


@dataclass(frozen=True)
class LessonChange:
    """A notice Librus shows on a lesson, with the details of its tooltip.

    ``type`` is the Librus text (zastępstwo, odwołane, ...); the swaps are the
    Librus texts "old -> new", empty when not given.
    """

    type: str
    teacher: str = ""
    subject: str = ""
    classroom: str = ""
    date_added: str = ""


@dataclass(frozen=True)
class Lesson:
    """One lesson of the timetable."""

    day: date
    number: int
    start: str
    end: str
    subject: str
    teacher: str
    classroom: str
    changes: tuple[LessonChange, ...] = ()

    @property
    def id(self) -> str:
        """Date and lesson number, "2026-10-21/3"."""
        return f"{self.day.isoformat()}/{self.number}"

    @property
    def cancelled(self) -> bool:
        """The lesson does not take place."""
        return any(
            change.type.lower().startswith(_CANCELLED) for change in self.changes
        )


@dataclass
class TimetableData:
    """Lessons of the read weeks (Mondays), in time order."""

    weeks: list[date]
    lessons: list[Lesson]


def week_mondays(today: date, weeks: int) -> list[date]:
    """Return the Monday of the current week and of the ``weeks`` weeks after it."""
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(weeks=week) for week in range(weeks + 1)]


def split_teacher(text: str) -> tuple[str, str]:
    """Split the library's "teacher s. classroom" text into teacher and classroom.

    Several lessons in one period come joined with " / " (groups); their teachers
    and classrooms are joined the same way.
    """
    teachers, classrooms = [], []
    for part in text.split(" / "):
        part = " ".join(part.split())
        if match := _TEACHER_CLASSROOM.fullmatch(part):
            teachers.append(match["teacher"] or "")
            classrooms.append(match["classroom"])
        else:
            teachers.append(part)
    return (
        " / ".join(teacher for teacher in teachers if teacher),
        " / ".join(classrooms),
    )


def _changes(info: dict) -> tuple[LessonChange, ...]:
    """Notices of a period: {label: ""} or {label: {teacher_swap, ...}}."""
    changes = []
    for label, details in info.items():
        if not label:
            continue
        if not isinstance(details, dict):
            details = {}
        changes.append(
            LessonChange(
                type=label,
                teacher=details.get("teacher_swap", "").strip(),
                subject=details.get("subject_swap", "").strip(),
                classroom=details.get("classroom_swap", "").strip(),
                date_added=details.get("date_added", "").strip(),
            )
        )
    return tuple(changes)


def _lesson(period: Period) -> Lesson | None:
    """The lesson of a period; None for an empty period."""
    subject = period.subject.strip()
    if not subject:
        return None
    teacher, classroom = split_teacher(period.teacher_and_classroom)
    return Lesson(
        day=date.fromisoformat(period.date),
        number=period.number,
        start=period.date_from.strip(),
        end=period.date_to.strip(),
        subject=subject,
        teacher=teacher,
        classroom=classroom,
        changes=_changes(period.info or {}),
    )


def read_timetable(client: Client, mondays: list[date]) -> TimetableData:
    """Read the timetable of each week (executor), one request per week.

    A week that cannot be parsed (for example during holidays) is skipped; if no
    week can be parsed, the page format changed and the update fails.
    """
    weeks, lessons = [], []
    for monday in mondays:
        try:
            week = get_timetable(client, monday)
        except (ParseError, DateError, IndexError, ValueError) as err:
            _LOGGER.debug("Timetable of the week of %s not read: %s", monday, err)
            continue
        weeks.append(monday)
        lessons.extend(
            lesson
            for day in week
            for period in day
            if (lesson := _lesson(period)) is not None
        )
    if mondays and not weeks:
        raise LibrusParseError("Cannot parse the timetable")
    return TimetableData(
        weeks, sorted(lessons, key=lambda item: (item.day, item.number))
    )
