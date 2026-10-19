"""Shared fixtures for the Librus APIX tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components in every test."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip the entry setup (for config flow tests)."""
    with patch(
        "custom_components.librus_apix.async_setup_entry", return_value=True
    ) as mock:
        yield mock
