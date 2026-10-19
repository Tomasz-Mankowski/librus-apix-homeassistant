"""Per-entry storage in .storage; it survives restarts.

Later tasks keep here what must not be lost on a restart: seen item ids,
baseline months, message bodies and schedule event details.
"""

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_VERSION = 1
SAVE_DELAY = 10  # seconds; one write for all changes of a poll


class LibrusStore:
    """JSON document of one entry, kept in memory and saved with a delay."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Prepare the store file librus_apix.<entry_id>."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.data: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Read the stored document (empty on the first start)."""
        self.data = await self._store.async_load() or {}

    @callback
    def async_schedule_save(self) -> None:
        """Save the document after SAVE_DELAY seconds (and on shutdown)."""
        self._store.async_delay_save(lambda: self.data, SAVE_DELAY)

    async def async_flush(self) -> None:
        """Save the document now (on unload, before a reload reads it)."""
        await self._store.async_save(self.data)

    async def async_remove(self) -> None:
        """Delete the store file."""
        await self._store.async_remove()
