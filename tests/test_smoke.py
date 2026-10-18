"""Smoke test: the Home Assistant test harness runs and the package imports."""

from homeassistant.core import HomeAssistant

from custom_components.librus_apix.const import DOMAIN


async def test_harness(hass: HomeAssistant) -> None:
    """The hass fixture is running and the integration constants import."""
    assert hass.is_running
    assert DOMAIN == "librus_apix"
