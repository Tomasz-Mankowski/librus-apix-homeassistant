"""Tests for the coordinator base: intervals and error mapping."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.const import CONF_INTERVAL_STUDENT
from custom_components.librus_apix.coordinator import (
    LibrusCoordinator,
    StudentInfoCoordinator,
)
from custom_components.librus_apix.exceptions import (
    LibrusAuthError,
    LibrusConnectionError,
    LibrusParseError,
    LibrusUnavailableError,
)


def _coordinator(
    hass: HomeAssistant, entry: MockConfigEntry, error: Exception
) -> StudentInfoCoordinator:
    """Coordinator with a 10 min interval whose API call raises ``error``."""
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_INTERVAL_STUDENT: 10}
    )
    api = MagicMock()
    api.async_call = AsyncMock(side_effect=error)
    return StudentInfoCoordinator(hass, entry, api)


async def test_rejected_login_raises_auth_failed(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """LibrusAuthError starts the reauth flow."""
    coordinator = _coordinator(hass, config_entry, LibrusAuthError("no"))

    with pytest.raises(ConfigEntryAuthFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.translation_key == "auth_failed"


@pytest.mark.parametrize(
    ("error", "key", "retry_after"),
    [
        (LibrusUnavailableError("refused", retry_after=7200), "unavailable", 7200),
        # 5 min backoff < 10 min interval: the normal interval stays.
        (LibrusUnavailableError("refused", retry_after=300), "unavailable", None),
        (LibrusUnavailableError("down", maintenance=True), "maintenance", None),
    ],
)
async def test_refused_requests_wait_for_the_backoff(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    error: Exception,
    key: str,
    retry_after: float | None,
) -> None:
    """A backoff longer than the interval delays the next poll."""
    coordinator = _coordinator(hass, config_entry, error)

    with pytest.raises(UpdateFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.translation_key == key
    assert exc.value.retry_after == retry_after


@pytest.mark.parametrize(
    "error", [LibrusConnectionError("timeout"), LibrusParseError("odd page")]
)
async def test_other_errors_fail_the_update(
    hass: HomeAssistant, config_entry: MockConfigEntry, error: Exception
) -> None:
    """Other Librus errors fail the update with the error text."""
    coordinator = _coordinator(hass, config_entry, error)

    with pytest.raises(UpdateFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.translation_key == "update_failed"
    assert exc.value.translation_placeholders == {"error": str(error)}


async def test_missing_option_uses_the_default(hass: HomeAssistant) -> None:
    """An entry without the option uses the default interval."""
    entry = MockConfigEntry(domain="librus_apix", options={})
    entry.add_to_hass(hass)

    coordinator = LibrusCoordinator(
        hass, entry, MagicMock(), "x", CONF_INTERVAL_STUDENT
    )

    assert coordinator.update_interval == timedelta(hours=24)
    with pytest.raises(NotImplementedError):
        await coordinator._async_fetch()
