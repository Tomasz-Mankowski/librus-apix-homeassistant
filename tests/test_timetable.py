"""Tests for the timetable: weeks, lesson records and the coordinator (F3)."""

from datetime import date, timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.const import (
    CONF_INTERVAL_TIMETABLE,
    CONF_TIMETABLE_WEEKS,
)
from custom_components.librus_apix.timetable import (
    Lesson,
    LessonChange,
    split_teacher,
    week_mondays,
)

from .common import FakeLesson, FakeServer

# Wednesday 2026-10-21 in Poland: the current week starts on Monday 2026-10-19.
NOW = "2026-10-21T08:00:00+00:00"


@pytest.fixture(autouse=True)
def frozen_today(freezer: FrozenDateTimeFactory) -> None:
    """Freeze the time in the middle of a week."""
    freezer.move_to(NOW)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: int) -> None:
    hass.config_entries.async_update_entry(entry, options={**entry.options, **options})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.parametrize(
    ("today", "weeks", "expected"),
    [
        (date(2026, 10, 21), 0, [date(2026, 10, 19)]),
        (date(2026, 10, 25), 1, [date(2026, 10, 19), date(2026, 10, 26)]),
        (
            date(2026, 10, 19),
            4,
            [date(2026, 10, 19) + timedelta(weeks=n) for n in range(5)],
        ),
        (date(2026, 12, 30), 1, [date(2026, 12, 28), date(2027, 1, 4)]),
    ],
)
def test_week_mondays(today: date, weeks: int, expected: list[date]) -> None:
    """The Monday of the current week and of the next ``weeks`` weeks."""
    assert week_mondays(today, weeks) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Adam Rachunek s. 12", ("Adam Rachunek", "12")),
        ("  Adam   Rachunek  s.  12 ", ("Adam Rachunek", "12")),
        ("Marek Biegowy s. sala gim.", ("Marek Biegowy", "sala gim.")),
        ("Anna Nowak-Kowalska s. 3", ("Anna Nowak-Kowalska", "3")),
        ("Anna Nowak", ("Anna Nowak", "")),
        ("s. 5", ("", "5")),
        ("", ("", "")),
        (
            "Kate Grammar s. 15 / Hans Wort s. 16",
            ("Kate Grammar / Hans Wort", "15 / 16"),
        ),
    ],
)
def test_teacher_and_classroom_are_split(text: str, expected: tuple[str, str]) -> None:
    """The library gives "teacher s. classroom" as one text (groups with " / ")."""
    assert split_teacher(text) == expected


async def test_lessons_of_the_current_and_next_week(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Default: this week and the next; changes kept; empty periods skipped."""
    await _setup(hass, config_entry)

    data = config_entry.runtime_data.timetable.data
    assert data.weeks == [date(2026, 10, 19), date(2026, 10, 26)]
    assert data.lessons == [
        Lesson(
            date(2026, 10, 19), 1, "08:00", "08:45", "Matematyka", "Adam Rachunek", "12"
        ),
        Lesson(
            date(2026, 10, 19),
            2,
            "08:55",
            "09:40",
            "Język polski",
            "Ewa Ortografia",
            "8",
        ),
        Lesson(
            date(2026, 10, 21),
            3,
            "09:50",
            "10:35",
            "Matematyka",
            "Zenon Zastępczy",
            "12",
            (
                LessonChange(
                    "zastępstwo",
                    teacher_swap="Adam Rachunek -> Zenon Zastępczy",
                    date_added="2026-10-18 12:00:00",
                ),
            ),
        ),
        Lesson(
            date(2026, 10, 27),
            3,
            "09:50",
            "10:35",
            "Historia",
            "Barbara Dawna",
            "10",
            (LessonChange("odwołane"),),
        ),
        Lesson(
            date(2026, 10, 29),
            1,
            "08:00",
            "08:45",
            "Język angielski",
            "Kate Grammar",
            "21",
            (LessonChange("zmiana sali", classroom_swap="15 -> 21"),),
        ),
    ]
    assert [lesson.cancelled for lesson in data.lessons] == [False] * 3 + [True, False]
    assert data.lessons[2].id == "2026-10-21/3"


@pytest.mark.parametrize("weeks", [0, 2, 4])
async def test_one_request_per_week(
    hass: HomeAssistant,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    weeks: int,
) -> None:
    """N weeks ahead: N + 1 timetable requests per poll, from the current week."""
    await _setup(hass, config_entry, **{CONF_TIMETABLE_WEEKS: weeks})
    coordinator = config_entry.runtime_data.timetable
    start = len(mock_server.mocker.request_history)

    await coordinator.async_refresh()

    mondays = [str(date(2026, 10, 19) + timedelta(weeks=n)) for n in range(weeks + 1)]
    assert mock_server.timetable_weeks(start) == mondays
    assert [str(monday) for monday in coordinator.data.weeks] == mondays
    days = {lesson.day for lesson in coordinator.data.lessons}
    assert (date(2026, 11, 2) in days) is (weeks >= 2)


async def test_interval_comes_from_the_options(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The timetable polls at its own interval (default 360 min)."""
    await _setup(hass, config_entry)
    assert config_entry.runtime_data.timetable.update_interval == timedelta(hours=6)

    await hass.config_entries.async_unload(config_entry.entry_id)
    await _setup(hass, config_entry, **{CONF_INTERVAL_TIMETABLE: 30})

    assert config_entry.runtime_data.timetable.update_interval == timedelta(minutes=30)


async def test_empty_notice_is_no_change(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """An empty notice box (as on the upstream mock pages) is not a change."""
    mock_server.lessons = [FakeLesson(date(2026, 10, 20), 1, "Fizyka", label="")]

    await _setup(hass, config_entry)

    [lesson] = config_entry.runtime_data.timetable.data.lessons
    assert (lesson.subject, lesson.changes, lesson.cancelled) == ("Fizyka", (), False)


async def test_unreadable_week_is_skipped(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A week without a timetable (holidays) is left out; the others stay."""
    mock_server.broken_weeks = {date(2026, 10, 26)}

    await _setup(hass, config_entry)

    coordinator = config_entry.runtime_data.timetable
    assert coordinator.last_update_success
    assert coordinator.data.weeks == [date(2026, 10, 19)]
    assert {lesson.day for lesson in coordinator.data.lessons} == {
        date(2026, 10, 19),
        date(2026, 10, 21),
    }


async def test_no_readable_week_fails_the_update(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """If no week can be parsed, the page format changed: the update fails."""
    mock_server.broken_weeks = {date(2026, 10, 19), date(2026, 10, 26)}

    await _setup(hass, config_entry)

    coordinator = config_entry.runtime_data.timetable
    assert not coordinator.last_update_success
    assert coordinator.data is None
    assert coordinator.last_exception.translation_key == "update_failed"
