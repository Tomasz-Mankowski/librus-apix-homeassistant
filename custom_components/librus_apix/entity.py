"""Base entity: one device per student (config entry)."""

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SERVER_URL, DOMAIN
from .coordinator import LibrusCoordinator

LIBRUS_URL = "https://synergia.librus.pl"


class LibrusEntity[C: LibrusCoordinator[Any]](CoordinatorEntity[C]):
    """Entity of a student device; the name comes from the translations."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: C, description: EntityDescription) -> None:
        """Bind the entity to the coordinator and the student device."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Librus Synergia",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=entry.data.get(CONF_SERVER_URL, LIBRUS_URL),
        )

    @property
    def available(self) -> bool:
        """Available after the first successful poll of the coordinator."""
        return super().available and self.coordinator.data is not None
