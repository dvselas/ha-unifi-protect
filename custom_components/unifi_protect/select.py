"""Select platform for UniFi Protect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera

_LOGGER = logging.getLogger(__name__)

VIDEO_MODE_OPTIONS = [
    "default",
    "highFps",
    "sport",
    "slowShutter",
    "lprReflex",
    "lprNoneReflex",
]

VIDEO_MODE_LABELS = {
    "default": "Default",
    "highFps": "High FPS",
    "sport": "Sport",
    "slowShutter": "Slow Shutter",
    "lprReflex": "LPR Reflex",
    "lprNoneReflex": "LPR None Reflex",
}

HDR_MODE_OPTIONS = ["auto", "on", "off"]

HDR_MODE_LABELS = {
    "auto": "Auto",
    "on": "On",
    "off": "Off",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect select entities."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SelectEntity] = []

    # Add video mode and HDR mode selects for each camera
    for camera_id, camera in coordinator.cameras.items():
        # Only add video mode if camera supports multiple modes
        if camera.feature_flags.get("videoModes") and len(camera.feature_flags["videoModes"]) > 1:
            entities.append(CameraVideoModeSelect(coordinator, camera_id, camera))

        # Only add HDR mode if camera supports HDR
        if camera.feature_flags.get("hasHdr"):
            entities.append(CameraHDRModeSelect(coordinator, camera_id, camera))

    async_add_entities(entities)


class CameraVideoModeSelect(CoordinatorEntity[ProtectDataUpdateCoordinator], SelectEntity):
    """Select entity for camera video mode."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_video_mode"
        self._attr_name = "Video Mode"
        self._attr_device_info = camera.device_info
        self._attr_icon = "mdi:video-box"

        # Use camera's supported video modes if available
        supported_modes = camera.feature_flags.get("videoModes", VIDEO_MODE_OPTIONS)
        self._attr_options = [VIDEO_MODE_LABELS.get(mode, mode) for mode in supported_modes]
        self._supported_modes = supported_modes

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
    def current_option(self) -> str:
        """Return the current video mode."""
        mode = self.camera.video_mode
        return VIDEO_MODE_LABELS.get(mode, mode)

    async def async_select_option(self, option: str) -> None:
        """Change the video mode."""
        # Convert label back to API value
        mode_value = None
        for mode, label in VIDEO_MODE_LABELS.items():
            if label == option:
                mode_value = mode
                break

        if mode_value is None:
            _LOGGER.error("Unknown video mode: %s", option)
            return

        try:
            await self.coordinator.api.update_camera(
                self.camera_id, video_mode=mode_value
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting video mode for %s: %s", self.entity_id, err)


class CameraHDRModeSelect(CoordinatorEntity[ProtectDataUpdateCoordinator], SelectEntity):
    """Select entity for camera HDR mode."""

    _attr_has_entity_name = True
    _attr_options = [HDR_MODE_LABELS[mode] for mode in HDR_MODE_OPTIONS]

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_hdr_mode"
        self._attr_name = "HDR Mode"
        self._attr_device_info = camera.device_info
        self._attr_icon = "mdi:hdr"

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
    def current_option(self) -> str:
        """Return the current HDR mode."""
        mode = self.camera.hdr_type
        return HDR_MODE_LABELS.get(mode, mode)

    async def async_select_option(self, option: str) -> None:
        """Change the HDR mode."""
        # Convert label back to API value
        mode_value = None
        for mode, label in HDR_MODE_LABELS.items():
            if label == option:
                mode_value = mode
                break

        if mode_value is None:
            _LOGGER.error("Unknown HDR mode: %s", option)
            return

        try:
            await self.coordinator.api.update_camera(
                self.camera_id, hdr_type=mode_value
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting HDR mode for %s: %s", self.entity_id, err)
