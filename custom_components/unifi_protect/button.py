"""Button platform for UniFi Protect."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera, ProtectChime

_LOGGER = logging.getLogger(__name__)


@dataclass
class ProtectButtonEntityDescription(ButtonEntityDescription):
    """Describes UniFi Protect button entity."""

    key: str = ""


CAMERA_BUTTONS: tuple[ProtectButtonEntityDescription, ...] = (
    ProtectButtonEntityDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
        entity_registry_enabled_default=False,  # Disabled by default
    ),
)

CHIME_BUTTONS: tuple[ProtectButtonEntityDescription, ...] = (
    ProtectButtonEntityDescription(
        key="play",
        name="Play Chime",
        icon="mdi:bell-ring",
    ),
    ProtectButtonEntityDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
        entity_registry_enabled_default=False,  # Disabled by default
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect buttons."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ProtectButtonEntity | ProtectChimeButtonEntity] = []

    # Add buttons for each camera
    for camera_id, camera in coordinator.cameras.items():
        for description in CAMERA_BUTTONS:
            entities.append(
                ProtectButtonEntity(
                    coordinator,
                    camera_id,
                    camera,
                    description,
                )
            )

    # Add buttons for each chime
    for chime_id, chime in coordinator.chimes.items():
        for description in CHIME_BUTTONS:
            entities.append(
                ProtectChimeButtonEntity(
                    coordinator,
                    chime_id,
                    chime,
                    description,
                )
            )

    async_add_entities(entities)


class ProtectButtonEntity(
    CoordinatorEntity[ProtectDataUpdateCoordinator], ButtonEntity
):
    """Representation of a UniFi Protect button."""

    _attr_has_entity_name = True
    entity_description: ProtectButtonEntityDescription

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
        description: ProtectButtonEntityDescription,
    ) -> None:
        """Initialize the button.

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

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            if self.entity_description.key == "reboot":
                _LOGGER.info("Rebooting camera %s", self.camera.name)
                # Note: Reboot may use the v1 API endpoint rather than integration API
                await self.coordinator.api.post(
                    f"/proxy/protect/integration/v1/cameras/{self.camera_id}/reboot"
                )
                await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error pressing button %s: %s", self.entity_id, err)


class ProtectChimeButtonEntity(
    CoordinatorEntity[ProtectDataUpdateCoordinator], ButtonEntity
):
    """Representation of a UniFi Protect chime button."""

    _attr_has_entity_name = True
    entity_description: ProtectButtonEntityDescription

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        chime_id: str,
        chime: ProtectChime,
        description: ProtectButtonEntityDescription,
    ) -> None:
        """Initialize the button.

        Args:
            coordinator: The data update coordinator
            chime_id: Chime ID
            chime: Chime data
            description: Entity description
        """
        super().__init__(coordinator)
        self.entity_description = description
        self.chime_id = chime_id
        self._attr_unique_id = f"{chime_id}_{description.key}"
        self._attr_device_info = chime.device_info

    @property
    def chime(self) -> ProtectChime:
        """Return the chime object."""
        return self.coordinator.chimes[self.chime_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.chime_id in self.coordinator.chimes
            and self.chime.is_connected
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            if self.entity_description.key == "play":
                _LOGGER.info("Playing chime %s", self.chime.name)
                await self.coordinator.api.play_chime(self.chime_id, repeat_times=1)
                # Optionally refresh to update last_ring
                await self.coordinator.async_request_refresh()

            elif self.entity_description.key == "reboot":
                _LOGGER.info("Rebooting chime %s", self.chime.name)
                await self.coordinator.api.reboot_chime(self.chime_id)
                await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error pressing chime button %s: %s", self.entity_id, err)
