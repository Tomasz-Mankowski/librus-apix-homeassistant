"""Diagnostics of one entry: settings, poll state and data counts (N2).

Redacted: login, password, the entry title (student name) and the unique id
(login). Data is counted, never copied: no names, texts, grades or cookies.
"""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import (
    STORE_BODIES,
    STORE_SCHEDULE_DETAILS,
    LibrusConfigEntry,
    LibrusCoordinator,
    LibrusData,
)
from .grades import grade_items
from .request_queue import async_get_request_queue

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "title", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LibrusConfigEntry
) -> dict[str, Any]:
    """Return the diagnostics of the entry."""
    data = entry.runtime_data
    coordinators: dict[str, LibrusCoordinator[Any]] = {
        "student": data.student,
        "lucky_number": data.lucky_number,
        "messages": data.messages,
        "announcements": data.announcements,
        "grades": data.grades,
        "schedule": data.schedule,
        "timetable": data.timetable,
    }
    stored = data.store.data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "connection": data.api.diagnostics(),
        "backoff": async_get_request_queue(hass).diagnostics(),
        "coordinators": {name: _coordinator(c) for name, c in coordinators.items()},
        "data": _counts(data),
        "store": {
            "trackers": {
                name: {"items": len(state["items"]), "scopes": state.get("scopes")}
                for name, state in stored.get("tracker", {}).items()
            },
            "message_bodies": len(stored.get(STORE_BODIES, {})),
            "schedule_details": len(stored.get(STORE_SCHEDULE_DETAILS, {})),
        },
    }


def _coordinator(coordinator: LibrusCoordinator[Any]) -> dict[str, Any]:
    """Poll state; an error is shown by its type only (texts may hold data)."""
    error = coordinator.last_exception
    cause = error.__cause__ if error else None
    interval = coordinator.update_interval
    return {
        "last_update_success": coordinator.last_update_success,
        "interval_minutes": interval.total_seconds() / 60 if interval else None,
        "has_data": coordinator.data is not None,
        "last_error": None
        if error is None
        else {
            "type": type(error).__name__,
            "translation_key": getattr(error, "translation_key", None),
            "cause": type(cause).__name__ if cause else None,
        },
    }


def _counts(data: LibrusData) -> dict[str, Any]:
    """How much data each coordinator holds (None before its first poll)."""
    student = data.student.data
    lucky = data.lucky_number.data
    messages = data.messages.data
    announcements = data.announcements.data
    grades = data.grades.data
    schedule = data.schedule.data
    timetable = data.timetable.data
    return {
        "student": None
        if student is None
        else {
            "fields": sorted(
                key for key, value in asdict(student.info).items() if value
            ),
            "bells": len(student.bells),
        },
        "lucky_number": None if lucky is None else {"shown": lucky.number is not None},
        "messages": None
        if messages is None
        else {
            "count": len(messages.messages),
            "unread": sum(message.unread for message in messages.messages),
        },
        "announcements": None
        if announcements is None
        else {"count": len(announcements.announcements)},
        "grades": None
        if grades is None
        else {
            "semester": grades.semester,
            "subjects": len(grades.subjects),
            "grades": len(grade_items(grades)),
            "final_grades": sum(len(s.finals) for s in grades.subjects.values()),
            "descriptive_grades": len(grades.descriptive_items()),
        },
        "schedule": None
        if schedule is None
        else {
            "months": [f"{year:04d}-{month:02d}" for year, month in schedule.months],
            "events": len(schedule.events),
            "types": sorted({event.type for event in schedule.events}),
        },
        "timetable": None
        if timetable is None
        else {
            "weeks": [monday.isoformat() for monday in timetable.weeks],
            "lessons": len(timetable.lessons),
            "changes": sorted(
                {
                    change.type
                    for lesson in timetable.lessons
                    for change in lesson.changes
                }
            ),
        },
    }
