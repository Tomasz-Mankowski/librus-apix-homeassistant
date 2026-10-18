"""Tests for the local brand images served by Home Assistant's brands integration."""

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.librus_apix.const import DOMAIN

BRAND_DIR = Path(__file__).parents[1] / "custom_components" / DOMAIN / "brand"


@pytest.mark.parametrize(
    "image", ["icon.png", "icon@2x.png", "dark_icon.png", "dark_icon@2x.png"]
)
async def test_brand_image_served(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, image: str
) -> None:
    """Home Assistant serves our own image, not the CDN placeholder."""
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()

    resp = await client.get(f"/api/brands/integration/{DOMAIN}/{image}?placeholder=no")

    assert resp.status == 200
    assert await resp.read() == (BRAND_DIR / image).read_bytes()
