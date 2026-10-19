"""Tests for the grade sensors per subject (F11, F13)."""

from unittest.mock import MagicMock

from bs4 import BeautifulSoup
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.const import DOMAIN
from custom_components.librus_apix.grades import (
    _number,
    _PageKeeper,
    _tooltip,
    read_final_grades,
)
from custom_components.librus_apix.sensor import SubjectSensor

from .common import FakeGrade, FakeServer, FakeSubject


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


def _state(hass: HomeAssistant, entry: MockConfigEntry, slug: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_grades_{slug}"
    )
    assert entity_id, slug
    return hass.states.get(entity_id)


async def test_one_sensor_per_subject_with_the_librus_averages(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """The state is the average Librus shows (not the calculated one)."""
    await _setup(hass, config_entry)

    math = _state(hass, config_entry, "matematyka")
    assert math.state == "3.69"
    assert math.attributes["friendly_name"] == "Zofia Testowa Matematyka"
    assert math.attributes["semester"] == 1
    assert math.attributes["average_source"] == "librus"
    assert math.attributes["averages"] == {
        "semester_1": 3.69,
        "semester_2": None,
        "year": 3.69,
    }
    assert _state(hass, config_entry, "jezyk_polski").state == "4.0"
    plastyka = _state(hass, config_entry, "plastyka")
    assert plastyka.state == STATE_UNKNOWN
    assert plastyka.attributes["average_source"] is None


async def test_grades_and_final_grades_with_all_details(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Every grade with its details; semester grades kept apart."""
    await _setup(hass, config_entry)

    attributes = _state(hass, config_entry, "matematyka").attributes
    grades = {g["id"]: g for g in attributes["grades"]["semester_1"]}
    assert sorted(grades) == ["1101", "1102", "1103", "1104", "1105"]
    assert attributes["grades"]["semester_2"] == []
    assert grades["1103"] == {
        "id": "1103",
        "grade": "1",
        "value": 1.0,
        "category": "Sprawdzian",
        "date": "2026-09-20",
        "weight": 3,
        "counts": True,
        "teacher": "Adam Rachunek",
        "comment": "Działania",
    }
    assert grades["1102"]["value"] == 4.5
    assert grades["1105"]["value"] is None
    assert grades["1105"]["counts"] is False
    assert attributes["final_grades"] == [
        {
            "period": "semester_1",
            "grade": "4",
            "proposed": True,
            "category": "Proponowana (śródroczna)",
            "date": "2026-10-15",
            "teacher": "Adam Rachunek",
            "id": "1190",
        }
    ]


@pytest.mark.parametrize(
    "hidden",
    [("-", "-", "-"), None],
    ids=["dash", "hidden by the school"],
)
async def test_hidden_averages_are_calculated(
    hass: HomeAssistant,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    hidden: tuple[str, str, str] | None,
) -> None:
    """Without Librus averages the state is calculated: (10+4.5+3+12)/9.

    None: empty cells without the "right" class, as on a school that hides
    averages; the library gives 0.0 for them (live test I-003).
    """
    for subject in mock_server.subjects:
        subject.averages = hidden

    await _setup(hass, config_entry)

    math = _state(hass, config_entry, "matematyka")
    assert float(math.state) == pytest.approx(29.5 / 9)
    assert math.attributes["average_source"] == "calculated"
    assert math.attributes["averages"]["semester_1"] == 3.28
    assert _state(hass, config_entry, "jezyk_polski").state == "4.0"
    art = _state(hass, config_entry, "plastyka")
    assert art.state == STATE_UNKNOWN
    assert art.attributes["average_source"] is None


async def test_second_semester_is_current_once_it_has_grades(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """One grade in semester 2 makes it the current semester for all subjects."""
    mock_server.subjects[1].semester2 = [FakeGrade(1301, "6", weight=1)]

    await _setup(hass, config_entry)

    polish = _state(hass, config_entry, "jezyk_polski")
    assert polish.attributes["semester"] == 2
    assert polish.state == "6.0"
    assert polish.attributes["average_source"] == "calculated"
    assert _state(hass, config_entry, "matematyka").state == STATE_UNKNOWN


async def test_new_subject_adds_a_sensor_without_reload(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A subject that appears later gets its sensor at the next poll."""
    await _setup(hass, config_entry)
    mock_server.subjects.append(
        FakeSubject("Informatyka", semester1=[FakeGrade(1401, "5")])
    )

    await config_entry.runtime_data.grades.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, config_entry, "informatyka").state == "5.0"


async def test_removed_subject_is_unavailable(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """A subject that leaves the page makes its sensor unavailable."""
    await _setup(hass, config_entry)
    mock_server.subjects.pop()

    await config_entry.runtime_data.grades.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, config_entry, "plastyka").state == STATE_UNAVAILABLE


async def test_one_grades_request_per_poll(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Grades, averages and final grades come from one page request."""
    await _setup(hass, config_entry)
    assert mock_server.paths().count("/przegladaj_oceny/uczen") == 1

    await config_entry.runtime_data.grades.async_refresh()

    assert mock_server.paths().count("/przegladaj_oceny/uczen") == 2


def test_grade_lists_are_not_recorded() -> None:
    """The grade lists stay out of the recorder."""
    assert {"grades", "final_grades"} <= SubjectSensor._unrecorded_attributes


def test_final_grades_only_from_subject_rows() -> None:
    """Rows without the toggle cell or with too few cells are skipped."""
    page = (
        '<table><tr class="line0"><td>no toggle</td></tr>'
        '<tr class="line1"><td class="center micro screen-only"></td>'
        "<td>Short</td><td></td></tr></table>"
    )

    assert read_final_grades(BeautifulSoup(page, "lxml")) == {}


def test_page_keeper_keeps_only_the_grades_page() -> None:
    """Other POST requests pass through without being kept."""
    client = MagicMock()
    client.GRADES_URL = "http://mock/przegladaj_oceny/uczen"
    client.post.return_value.text = "page"
    keeper = _PageKeeper(client)

    keeper.post("http://mock/other", {})
    assert keeper.page == ""
    keeper.post(client.GRADES_URL, {})
    assert keeper.page == "page"
    assert keeper.INFO_URL is client.INFO_URL


def test_tooltip_parts_without_a_value_are_skipped() -> None:
    """Only "key: value" parts of a tooltip are read."""
    tag = BeautifulSoup(
        '<a title="Kategoria: Test<br>bez wartości<br/>Waga: 2">', "lxml"
    ).a

    assert _tooltip(tag) == {"Kategoria": "Test", "Waga": "2"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3,69", 3.69),
        ("4.00", 4.0),
        ("-", None),
        ("", None),
        ("0.00", None),
        (0.0, None),
    ],
)
def test_librus_average_only_when_shown(
    value: float | str, expected: float | None
) -> None:
    """0 is no average: the library's 0.0 for missing cells, or Librus' "0.00"."""
    assert _number(value) == expected
