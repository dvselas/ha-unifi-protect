"""Switch platform for UniFi Protect."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera

_LOGGER = logging.getLogger(__name__)


@dataclass
class ProtectSwitchEntityDescription(SwitchEntityDescription):
    """Describes UniFi Protect switch entity."""

    key: str = ""


CAMERA_SWITCHES: tuple[ProtectSwitchEntityDescription, ...] = (
    ProtectSwitchEntityDescription(
        key="privacy_mode",
        name="Privacy Mode",
        icon="mdi:eye-off",
    ),
    ProtectSwitchEntityDescription(
        key="recording",
        name="Recording",
        icon="mdi:record-rec",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect switches."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ProtectSwitchEntity] = []

    # Add switches for each camera
    for camera_id, camera in coordinator.cameras.items():
        for description in CAMERA_SWITCHES:
            entities.append(
                ProtectSwitchEntity(
                    coordinator,
                    camera_id,
                    camera,
                    description,
                )
            )

    async_add_entities(entities)


class ProtectSwitchEntity(
    CoordinatorEntity[ProtectDataUpdateCoordinator], SwitchEntity
):
    """Representation of a UniFi Protect switch."""

    _attr_has_entity_name = True
    entity_description: ProtectSwitchEntityDescription

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
        description: ProtectSwitchEntityDescription,
    ) -> None:
        """Initialize the switch.

        Args:
            coordinator: The data update coordinator
            camera_id: Camera ID
            camera: Camera data
            description: Entity description
        """
        super().__init__(coordinator)
        self.entity_description = description
        self.camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_{description.key}"
        self._attr_device_info = camera.device_info

    @property
    def camera(self) -> ProtectCamera:
        """Return the camera object."""
        return self.coordinator.cameras[self.camera_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.camera_id in self.coordinator.cameras
            and self.camera.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if self.entity_description.key == "privacy_mode":
            return self.camera.privacy_mode
        elif self.entity_description.key == "recording":
            return self.camera.recording_mode != "never"

        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            if self.entity_description.key == "privacy_mode":
                await self.coordinator.api.set_privacy_mode(self.camera_id, True)
            elif self.entity_description.key == "recording":
                await self.coordinator.api.set_recording_mode(
                    self.camera_id, "always"
                )

            # Request coordinator update
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error turning on %s: %s", self.entity_id, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            if self.entity_description.key == "privacy_mode":
                await self.coordinator.api.set_privacy_mode(self.camera_id, False)
            elif self.entity_description.key == "recording":
                await self.coordinator.api.set_recording_mode(
                    self.camera_id, "never"
                )

            # Request coordinator update
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error turning off %s: %s", self.entity_id, err)
