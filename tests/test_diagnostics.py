"""Tests for the diagnostics (N2: no credentials or personal data)."""

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.librus_apix.request_queue import DATA_REQUEST_QUEUE

from .common import MOCK_URL, SCHOOL, FakeServer


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_no_credentials_cookies_or_personal_data(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """Login, password, cookies, names and school are not in the diagnostics."""
    await _setup(hass, config_entry)
    config_entry.runtime_data.api.client._session.cookies.set(
        "DZIENNIKSID", "cookie-value-123"
    )

    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    text = json.dumps(result, ensure_ascii=False)
    for secret in (
        "zofia.testowa",
        "secret",
        "cookie-value-123",
        "Zofia",
        "Testowa",
        "Magdalena Przykładowa",
        SCHOOL.splitlines()[0],
        "Ułamki",
        "Adam Rachunek",
    ):
        assert secret not in text, secret
    assert result["entry"]["data"]["username"] == "**REDACTED**"
    assert result["entry"]["data"]["password"] == "**REDACTED**"
    assert result["entry"]["title"] == "**REDACTED**"
    assert result["entry"]["unique_id"] == "**REDACTED**"


async def test_poll_state_and_counts(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """Each coordinator, the data counts and the store sizes are shown."""
    await _setup(hass, config_entry)

    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    assert result["connection"] == {
        "host": MOCK_URL.removeprefix("http://"),
        "mock": True,
        "logged_in": True,
    }
    assert result["backoff"] == {}
    assert set(result["coordinators"]) == {
        "student",
        "lucky_number",
        "messages",
        "announcements",
        "grades",
        "schedule",
        "timetable",
    }
    assert result["coordinators"]["schedule"] == {
        "last_update_success": True,
        "interval_minutes": 60.0,
        "has_data": True,
        "last_error": None,
    }
    data = result["data"]
    assert data["student"] == {
        "fields": ["class_name", "lucky_number", "name", "number", "school", "tutor"],
        "bells": 3,
    }
    assert data["lucky_number"] == {"shown": True}
    assert result["coordinators"]["lucky_number"]["interval_minutes"] == 180.0
    # This week and the next (the lessons depend on today's date).
    assert len(data["timetable"]["weeks"]) == 2
    assert set(data["timetable"]) == {"weeks", "lessons", "changes"}
    assert data["messages"]["count"] == len(mock_server.messages)
    assert data["grades"]["subjects"] == len(mock_server.subjects)
    assert data["schedule"]["events"] > 0
    assert "Sprawdzian" in data["schedule"]["types"]
    assert set(result["store"]["trackers"]) >= {"messages", "grades", "schedule"}


async def test_failed_poll_shows_the_error_type_only(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_server: FakeServer,
    config_entry: MockConfigEntry,
) -> None:
    """A failed poll: error type and translation key, not its text."""
    await _setup(hass, config_entry)
    mock_server.mocker.get(
        f"{MOCK_URL}/ogloszenia", status_code=503, text="zofia.testowa down"
    )
    await config_entry.runtime_data.announcements.async_refresh()

    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    assert result["coordinators"]["announcements"]["last_update_success"] is False
    assert result["coordinators"]["announcements"]["last_error"] == {
        "type": "UpdateFailed",
        "translation_key": "unavailable",
        "cause": "LibrusUnavailableError",
    }
    host = MOCK_URL.removeprefix("http://")
    assert result["backoff"][host]["failures"] == 1
    assert result["backoff"][host]["seconds_left"] > 0
    assert hass.data[DATA_REQUEST_QUEUE].diagnostics() == result["backoff"]
    assert "zofia.testowa" not in json.dumps(result)
