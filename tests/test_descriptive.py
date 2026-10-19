"""Tests for the descriptive grades: sensors per subject and the event (F12)."""

from typing import Any

from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from librus_apix import urls
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.librus_apix.const import DOMAIN
from custom_components.librus_apix.event import DescriptiveGradesEvent
from custom_components.librus_apix.sensor import DescriptiveSensor

from .common import MOCK_URL, FakeDescriptive, FakeServer

# Gateway API replies as the library expects them (librus-apix 1.6.0,
# grades._extract_grades_descriptive_from_api); not recorded from a real school.
GATEWAY = {
    "token": {"UserIdentifier": "u1"},
    "user": {"IdentifierOfStudentAssignedWithUser": "s1"},
    "grades": {
        "data": [
            {
                "semester": "1",
                "subjectId": "subject-uuid",
                "scaleValue": {"value": "B"},
                "teacherId": "t1",
                "date": "2026-10-10T08:00:00",
                "area": {"name": "Czytanie"},
                "content": "Czyta płynnie i ze zrozumieniem.",
                "addedBy": "t1",
                "comments": "",
            },
            {"semester": "3", "subjectId": "subject-uuid"},
        ]
    },
    "subjects": {
        "data": [
            {
                "identifier": "subject-uuid",
                "numericIdentifier": 501,
                "name": "Edukacja polonistyczna (API)",
            }
        ]
    },
    "users": {"Users": [{"AccountId": "t1", "LastName": "Nowak", "FirstName": "Ewa"}]},
}


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> list:
    events = async_capture_events(hass, EVENT_STATE_CHANGED)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return events


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str):
    return er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_{key}"
    )


def _fired(hass: HomeAssistant, entry: MockConfigEntry, events: list) -> list[dict]:
    entity_id = _entity_id(hass, entry, "event", "descriptive_grades")
    return [
        dict(e.data["new_state"].attributes)
        for e in events
        if e.data["entity_id"] == entity_id
        and e.data["new_state"].attributes.get(ATTR_EVENT_TYPE)
    ]


async def test_sensor_per_subject_with_all_details(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Old schema: the state is the number of grades; the grades have all details."""
    await _setup(hass, config_entry)

    entity_id = _entity_id(
        hass, config_entry, "sensor", "descriptive_edukacja_zdrowotna"
    )
    state = hass.states.get(entity_id)
    assert state.state == "2"
    assert state.attributes["friendly_name"] == (
        "Zofia Testowa Edukacja zdrowotna \N{EN DASH} descriptive grades"
    )
    first = state.attributes["grades"]["semester_1"][0]
    assert first == {
        "id": first["id"],
        "subject": "Edukacja zdrowotna",
        "semester": 1,
        "grade": "OP",
        "date": "2026-09-23",
        "teacher": "Magdalena Przykładowa",
        "content": "Zna zasady zdrowego odżywiania.",
        "description": first["description"],
    }
    assert "Treść oceny: Zna zasady" in first["description"]
    assert state.attributes["grades"]["semester_2"] == []


async def test_no_sensor_without_descriptive_grades(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A student without descriptive grades gets no descriptive sensor."""
    mock_server.descriptive = []

    await _setup(hass, config_entry)

    entities = er.async_entries_for_config_entry(
        er.async_get(hass), config_entry.entry_id
    )
    assert not [
        e for e in entities if e.domain == "sensor" and "_descriptive_" in e.unique_id
    ]


def test_texts_are_not_recorded() -> None:
    """Lists and event texts stay out of the recorder."""
    assert "grades" in DescriptiveSensor._unrecorded_attributes
    assert {"content", "description"} <= DescriptiveGradesEvent._unrecorded_attributes


async def test_new_descriptive_grade_fires_one_event(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The first poll fires nothing; a new descriptive grade fires one event."""
    events = await _setup(hass, config_entry)
    assert _fired(hass, config_entry, events) == []
    mock_server.descriptive[0].grades.append(
        FakeDescriptive("DB", "2026-10-18", "Dobra praca w grupie.", semester=1)
    )

    await config_entry.runtime_data.grades.async_refresh()
    await hass.async_block_till_done()

    [fired] = _fired(hass, config_entry, events)
    expected = {
        "event_type": "new_descriptive_grade",
        "subject": "Edukacja zdrowotna",
        "grade": "DB",
        "date": "2026-10-18",
        "content": "Dobra praca w grupie.",
        "student": "Zofia Testowa",
        "config_entry_id": config_entry.entry_id,
    }
    assert expected.items() <= fired.items()


async def test_new_schema_grades_from_the_gateway_api(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """New schema: the grades come from the gateway API (mocked JSON)."""
    mocker = mock_server.mocker
    mock_server.descriptive = []
    mock_server.new_schema = {501: "Edukacja polonistyczna"}
    mocker.get(f"{MOCK_URL}/refreshToken", cookies={"oauth_token": "token"})
    mocker.get(urls.GATEWAY_API_TOKEN_INFO, json=GATEWAY["token"])
    mocker.get(f"{urls.GATEWAY_API_USER_INFO}u1", json=GATEWAY["user"])
    mocker.post(f"{urls.GATEWAY_API_DESCRIPTIVE_GRADES}s1", json=GATEWAY["grades"])
    mocker.get(urls.GATEWAY_API_SUBJECTS, json=GATEWAY["subjects"])
    mocker.get(urls.GATEWAY_API_USERS, json=GATEWAY["users"])

    await _setup(hass, config_entry)

    entity_id = _entity_id(
        hass, config_entry, "sensor", "descriptive_edukacja_polonistyczna"
    )
    state = hass.states.get(entity_id)
    assert state.state == "1"
    grade: dict[str, Any] = state.attributes["grades"]["semester_1"][0]
    assert grade["grade"] == "B"
    assert grade["date"] == "2026-10-10"
    assert grade["teacher"] == "Nowak Ewa"
    assert grade["content"] == "Czyta płynnie i ze zrozumieniem."
    assert "Obszar: Czytanie" in grade["description"]
