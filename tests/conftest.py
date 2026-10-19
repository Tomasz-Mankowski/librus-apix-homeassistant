"""Shared fixtures for the Librus APIX tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import requests_mock as rm

from custom_components.librus_apix.const import (
    CONF_SERVER_URL,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from custom_components.librus_apix.request_queue import (
    DATA_REQUEST_QUEUE,
    RequestQueue,
)

from .common import MOCK_URL, FakeServer


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components in every test."""


@pytest.fixture(autouse=True)
def no_request_gap(hass: HomeAssistant) -> None:
    """Use a request queue without the gap between requests."""
    hass.data[DATA_REQUEST_QUEUE] = RequestQueue(hass, gap=0)


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip the entry setup and unload (for config flow tests)."""
    with (
        patch(
            "custom_components.librus_apix.async_setup_entry", return_value=True
        ) as mock,
        patch("custom_components.librus_apix.async_unload_entry", return_value=True),
    ):
        yield mock


@pytest.fixture
def mock_server(requests_mock: rm.Mocker) -> FakeServer:
    """Serve the Synergia pages of mock A (student info, messages)."""
    return FakeServer(requests_mock)


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """An entry for mock A with the default options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Zofia Testowa",
        unique_id="zofia.testowa",
        data={
            CONF_USERNAME: "zofia.testowa",
            CONF_PASSWORD: "secret",
            CONF_SERVER_URL: MOCK_URL,
        },
        options=dict(DEFAULT_OPTIONS),
    )
    entry.add_to_hass(hass)
    return entry
