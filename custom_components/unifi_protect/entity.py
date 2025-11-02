"""Base entity for UniFi Protect."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera


class ProtectDeviceEntity(CoordinatorEntity[ProtectDataUpdateCoordinator]):
    """Base entity for UniFi Protect devices."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        device: ProtectCamera,
    ) -> None:
        """Initialize the entity.

        Args:
            coordinator: The data update coordinator
            device: The Protect device
        """
        super().__init__(coordinator)
        self.device = device
        self._attr_unique_id = f"{device.id}_{self.entity_description.key}"
        self._attr_device_info = device.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.device.is_connected
