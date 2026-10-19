"""Tests for the Librus APIX config flow."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from librus_apix.student_information import StudentInformation
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import requests_mock as rm

from custom_components.librus_apix.const import (
    CONF_INTERVAL_ANNOUNCEMENTS,
    CONF_INTERVAL_GRADES,
    CONF_INTERVAL_MESSAGES,
    CONF_INTERVAL_SCHEDULE,
    CONF_INTERVAL_STUDENT,
    CONF_MESSAGE_COUNT,
    CONF_SERVER_URL,
    CONF_TIMEFRAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    SECTION_DEVELOPER,
)
from custom_components.librus_apix.exceptions import (
    LibrusAuthError,
    LibrusConnectionError,
    LibrusParseError,
    LibrusUnavailableError,
)

from .common import MOCK_URL, info_page

STUDENT = StudentInformation(
    "Zofia Testowa", "5a", 14, "Magdalena Przykładowa", "SP 999", 7
)
LOGIN = {CONF_USERNAME: "zofia.testowa", CONF_PASSWORD: "secret", SECTION_DEVELOPER: {}}
INFO_PAGE = info_page()


@pytest.fixture
def mock_api() -> Generator[MagicMock]:
    """Replace LibrusApi in the flow; the login check returns STUDENT."""
    with patch("custom_components.librus_apix.config_flow.LibrusApi") as api_cls:
        api_cls.return_value.async_call = AsyncMock(return_value=STUDENT)
        yield api_cls


async def _configure(hass: HomeAssistant, flow_id: str, data: dict) -> dict[str, Any]:
    return await hass.config_entries.flow.async_configure(flow_id, data)


async def _start(hass: HomeAssistant) -> dict[str, Any]:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def _settings_step(hass: HomeAssistant) -> dict[str, Any]:
    result = await _start(hass)
    result = await _configure(hass, result["flow_id"], LOGIN)
    assert result["step_id"] == "settings"
    return result


async def test_full_flow_with_defaults(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Login form, settings form with defaults, entry titled with the student."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await _configure(
        hass, result["flow_id"], {**LOGIN, CONF_USERNAME: "  Zofia.Testowa "}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "settings"

    result = await _configure(hass, result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zofia Testowa"
    assert result["data"] == {CONF_USERNAME: "Zofia.Testowa", CONF_PASSWORD: "secret"}
    assert result["options"] == DEFAULT_OPTIONS
    assert result["result"].unique_id == "zofia.testowa"
    mock_api.assert_called_once_with(hass, "Zofia.Testowa", "secret", base_url=None)
    assert len(mock_setup_entry.mock_calls) == 1


async def test_settings_are_stored_as_options(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Chosen settings become the entry options (whole numbers)."""
    settings = {
        CONF_INTERVAL_STUDENT: 720,
        CONF_INTERVAL_GRADES: 30,
        CONF_INTERVAL_MESSAGES: 10,
        CONF_INTERVAL_ANNOUNCEMENTS: 1440,
        CONF_INTERVAL_SCHEDULE: 120,
        CONF_TIMEFRAME: 6,
        CONF_MESSAGE_COUNT: 100,
    }
    result = await _settings_step(hass)

    result = await _configure(hass, result["flow_id"], settings)

    assert result["options"] == settings
    assert all(type(value) is int for value in result["options"].values())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (CONF_INTERVAL_GRADES, 9),
        (CONF_INTERVAL_STUDENT, 1441),
        (CONF_INTERVAL_SCHEDULE, 0),
        (CONF_TIMEFRAME, -1),
        (CONF_TIMEFRAME, 7),
        (CONF_MESSAGE_COUNT, 0),
        (CONF_MESSAGE_COUNT, 101),
    ],
)
async def test_settings_out_of_range_are_rejected(
    hass: HomeAssistant, mock_api: MagicMock, key: str, value: int
) -> None:
    """Intervals under 10 min, timeframe outside 0-6, count outside 1-100."""
    result = await _settings_step(hass)

    with pytest.raises(InvalidData):
        await _configure(hass, result["flow_id"], {**DEFAULT_OPTIONS, key: value})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (CONF_INTERVAL_MESSAGES, 10),
        (CONF_INTERVAL_STUDENT, 1440),
        (CONF_TIMEFRAME, 0),
        (CONF_TIMEFRAME, 6),
        (CONF_MESSAGE_COUNT, 1),
        (CONF_MESSAGE_COUNT, 100),
    ],
)
async def test_settings_limits_are_accepted(
    hass: HomeAssistant,
    mock_api: MagicMock,
    mock_setup_entry: AsyncMock,
    key: str,
    value: int,
) -> None:
    """The limits themselves are valid."""
    result = await _settings_step(hass)

    result = await _configure(hass, result["flow_id"], {**DEFAULT_OPTIONS, key: value})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][key] == value


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (LibrusAuthError("wrong password"), "invalid_auth"),
        (LibrusConnectionError("timeout"), "cannot_connect"),
        (LibrusUnavailableError("HTTP 503"), "cannot_connect"),
        (LibrusUnavailableError("maintenance", maintenance=True), "maintenance"),
        (LibrusParseError("unexpected page"), "unknown"),
        (RuntimeError("bug"), "unknown"),
    ],
)
async def test_login_errors_are_shown_and_can_be_fixed(
    hass: HomeAssistant,
    mock_api: MagicMock,
    mock_setup_entry: AsyncMock,
    error: Exception,
    key: str,
) -> None:
    """A failed login check shows the error; a new try continues."""
    mock_api.return_value.async_call.side_effect = error
    result = await _start(hass)

    result = await _configure(hass, result["flow_id"], LOGIN)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": key}

    mock_api.return_value.async_call.side_effect = None
    result = await _configure(hass, result["flow_id"], LOGIN)
    assert result["step_id"] == "settings"


async def test_invalid_server_url(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """A server URL without http:// or https:// is rejected before any request."""
    result = await _start(hass)

    result = await _configure(
        hass,
        result["flow_id"],
        {**LOGIN, SECTION_DEVELOPER: {CONF_SERVER_URL: "librus-mock-a:8000"}},
    )

    assert result["errors"] == {"base": "invalid_url"}
    mock_api.assert_not_called()


async def test_server_url_is_stored(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """The server URL is trimmed, used for the check and stored."""
    result = await _start(hass)
    result = await _configure(
        hass,
        result["flow_id"],
        {**LOGIN, SECTION_DEVELOPER: {CONF_SERVER_URL: f" {MOCK_URL}/ "}},
    )

    result = await _configure(hass, result["flow_id"], {})

    assert result["data"][CONF_SERVER_URL] == MOCK_URL
    mock_api.assert_called_once_with(hass, "zofia.testowa", "secret", base_url=MOCK_URL)


async def test_same_login_twice_aborts(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """A login already set up (any letter case) aborts without a request."""
    MockConfigEntry(domain=DOMAIN, unique_id="zofia.testowa").add_to_hass(hass)
    result = await _start(hass)

    result = await _configure(
        hass, result["flow_id"], {**LOGIN, CONF_USERNAME: "ZOFIA.testowa"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_api.assert_not_called()


async def test_flow_against_a_mock_server(
    hass: HomeAssistant, requests_mock: rm.Mocker, mock_setup_entry: AsyncMock
) -> None:
    """Without patches: the real client reads the student name from a mock server."""
    requests_mock.get(f"{MOCK_URL}/informacja", text=INFO_PAGE)
    result = await _start(hass)
    result = await _configure(
        hass,
        result["flow_id"],
        {**LOGIN, SECTION_DEVELOPER: {CONF_SERVER_URL: MOCK_URL}},
    )

    result = await _configure(hass, result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zofia Testowa"
    assert requests_mock.call_count == 1


async def _loaded_entry(hass: HomeAssistant, **options: int) -> MockConfigEntry:
    """Add and set up an entry for mock A."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Zofia Testowa",
        unique_id="zofia.testowa",
        data={
            CONF_USERNAME: "zofia.testowa",
            CONF_PASSWORD: "old",
            CONF_SERVER_URL: MOCK_URL,
        },
        options={**DEFAULT_OPTIONS, **options},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_reauth_updates_the_password_and_reloads(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """A correct login of the same account updates the entry and reloads it."""
    entry = await _loaded_entry(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"] == {"name": "Zofia Testowa"}

    result = await _configure(
        hass,
        result["flow_id"],
        {CONF_USERNAME: " Zofia.Testowa ", CONF_PASSWORD: "new"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == {
        CONF_USERNAME: "Zofia.Testowa",
        CONF_PASSWORD: "new",
        CONF_SERVER_URL: MOCK_URL,
    }
    mock_api.assert_called_once_with(hass, "Zofia.Testowa", "new", base_url=MOCK_URL)
    assert len(mock_setup_entry.mock_calls) == 2


async def test_reauth_with_another_login_aborts(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Another account aborts with unique_id_mismatch; the entry stays as it was."""
    entry = await _loaded_entry(hass)
    result = await entry.start_reauth_flow(hass)

    result = await _configure(
        hass, result["flow_id"], {CONF_USERNAME: "other.student", CONF_PASSWORD: "x"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert entry.data[CONF_PASSWORD] == "old"
    mock_api.assert_not_called()


async def test_reauth_error_is_shown_and_can_be_fixed(
    hass: HomeAssistant, mock_api: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """A wrong password shows invalid_auth; the next try succeeds."""
    entry = await _loaded_entry(hass)
    result = await entry.start_reauth_flow(hass)
    mock_api.return_value.async_call.side_effect = LibrusAuthError("wrong")
    login = {CONF_USERNAME: "zofia.testowa", CONF_PASSWORD: "typo"}

    result = await _configure(hass, result["flow_id"], login)
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}

    mock_api.return_value.async_call.side_effect = None
    result = await _configure(hass, result["flow_id"], login)
    assert result["reason"] == "reauth_successful"


async def test_options_show_current_values_and_saving_reloads(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The form starts with the current values; saving stores them and reloads."""
    entry = await _loaded_entry(hass, **{CONF_INTERVAL_GRADES: 30, CONF_TIMEFRAME: 3})

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # An empty submit keeps the pre-filled values.
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert entry.options == {
        **DEFAULT_OPTIONS,
        CONF_INTERVAL_GRADES: 30,
        CONF_TIMEFRAME: 3,
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**entry.options, CONF_INTERVAL_MESSAGES: 45, CONF_MESSAGE_COUNT: 50},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_INTERVAL_MESSAGES] == 45
    assert entry.options[CONF_MESSAGE_COUNT] == 50
    assert len(mock_setup_entry.mock_calls) == 2


async def test_options_out_of_range_are_rejected(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The options use the same limits as the setup."""
    entry = await _loaded_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {**DEFAULT_OPTIONS, CONF_INTERVAL_GRADES: 5}
        )
