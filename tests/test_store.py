"""Tests for the per-entry store."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.librus_apix.store import SAVE_DELAY, LibrusStore


async def test_empty_on_first_start(hass: HomeAssistant) -> None:
    """Without a file the document is empty."""
    store = LibrusStore(hass, "entry1")

    await store.async_load()

    assert store.data == {}


async def test_save_is_delayed(
    hass: HomeAssistant, hass_storage: dict, freezer: FrozenDateTimeFactory
) -> None:
    """Changes are written once, SAVE_DELAY seconds after the request."""
    store = LibrusStore(hass, "entry1")
    await store.async_load()
    store.data["seen"] = {"messages": [5001]}

    store.async_schedule_save()
    assert "librus_apix.entry1" not in hass_storage

    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass_storage["librus_apix.entry1"]["data"] == {"seen": {"messages": [5001]}}
