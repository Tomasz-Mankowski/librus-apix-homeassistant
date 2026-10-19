"""Tests for the GPA sensor and the average rules (F13)."""

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.const import (
    CONF_AVERAGE_MINUS,
    CONF_AVERAGE_PLUS,
    CONF_AVERAGE_WEIGHTS,
    DOMAIN,
)

from .common import FakeGrade, FakeServer


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id, key
    return hass.states.get(entity_id)


def _hide_averages(server: FakeServer) -> None:
    for subject in server.subjects:
        subject.averages = ("-", "-", "-")


async def test_gpa_from_the_librus_averages(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Mean of the averages Librus shows; subjects without one are skipped."""
    await _setup(hass, config_entry)

    gpa = _state(hass, config_entry, "gpa")
    assert float(gpa.state) == pytest.approx((3.69 + 4.0) / 2)
    assert gpa.attributes["friendly_name"] == "Zofia Testowa GPA"
    assert gpa.attributes["semester"] == 1
    assert gpa.attributes["average_source"] == "librus"
    assert gpa.attributes["subjects"] == {"Matematyka": 3.69, "Język polski": 4.0}
    mean = round((3.69 + 4.0) / 2, 2)
    assert gpa.attributes["averages"] == {
        "semester_1": mean,
        "semester_2": None,
        "year": mean,
    }


async def test_gpa_calculated_when_librus_shows_none(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Hidden averages: GPA of the calculated subject averages."""
    _hide_averages(mock_server)

    await _setup(hass, config_entry)

    gpa = _state(hass, config_entry, "gpa")
    assert float(gpa.state) == pytest.approx((29.5 / 9 + 4.0) / 2)
    assert gpa.attributes["average_source"] == "calculated"


async def test_gpa_source_mixed(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """Some subjects shown by Librus, some calculated."""
    mock_server.subjects[1].averages = ("-", "-", "-")

    await _setup(hass, config_entry)

    assert _state(hass, config_entry, "gpa").attributes["average_source"] == "mixed"


async def test_gpa_without_grades_is_unknown(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """No subject average: no GPA."""
    mock_server.subjects = mock_server.subjects[2:]

    await _setup(hass, config_entry)

    gpa = _state(hass, config_entry, "gpa")
    assert gpa.state == STATE_UNKNOWN
    assert gpa.attributes["average_source"] is None


async def test_gpa_of_the_second_semester(
    hass: HomeAssistant, mock_server: FakeServer, config_entry: MockConfigEntry
) -> None:
    """In semester 2 the GPA uses the semester-2 averages."""
    _hide_averages(mock_server)
    mock_server.subjects[1].semester2 = [FakeGrade(1301, "6")]

    await _setup(hass, config_entry)

    gpa = _state(hass, config_entry, "gpa")
    assert gpa.attributes["semester"] == 2
    assert gpa.state == "6.0"


@pytest.mark.parametrize(
    ("options", "math"),
    [
        # 4+ = 4.25 with plus 0.25: (10 + 4.25 + 3 + 12) / 9
        ({CONF_AVERAGE_PLUS: 0.25}, 29.25 / 9),
        # Without weights: (5 + 4.5 + 1 + 4) / 4
        ({CONF_AVERAGE_WEIGHTS: False}, 14.5 / 4),
        # Minus values do not change these grades
        ({CONF_AVERAGE_MINUS: 0.5}, 29.5 / 9),
    ],
)
async def test_average_rules_from_the_options(
    hass: HomeAssistant,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
    options: dict,
    math: float,
) -> None:
    """The rules in the options change the calculated averages."""
    _hide_averages(mock_server)
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, **options}
    )

    await _setup(hass, config_entry)

    state = _state(hass, config_entry, "grades_matematyka")
    assert float(state.state) == pytest.approx(math)
    gpa = _state(hass, config_entry, "gpa")
    assert float(gpa.state) == pytest.approx((math + 4.0) / 2)
