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
from .models import ProtectCamera, ProtectChime

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

LCD_MESSAGE_TYPE_OPTIONS = ["LEAVE_PACKAGE_AT_DOOR", "DO_NOT_DISTURB", "CUSTOM_MESSAGE"]

LCD_MESSAGE_TYPE_LABELS = {
    "LEAVE_PACKAGE_AT_DOOR": "Leave Package at Door",
    "DO_NOT_DISTURB": "Do Not Disturb",
    "CUSTOM_MESSAGE": "Custom Message",
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
        if len(camera.supported_video_modes) > 1:
            entities.append(CameraVideoModeSelect(coordinator, camera_id, camera))

        # Only add HDR mode if camera supports HDR
        if camera.supports_hdr:
            entities.append(CameraHDRModeSelect(coordinator, camera_id, camera))

        # Add LCD message select for doorbell cameras
        if camera.is_doorbell and camera.lcd_message:
            entities.append(DoorbellLCDMessageSelect(coordinator, camera_id, camera))

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
        supported_modes = camera.supported_video_modes if camera.supported_video_modes else VIDEO_MODE_OPTIONS
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


class DoorbellLCDMessageSelect(CoordinatorEntity[ProtectDataUpdateCoordinator], SelectEntity):
    """Select entity for doorbell LCD message."""

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
        self._attr_unique_id = f"{camera_id}_lcd_message"
        self._attr_name = "LCD Message"
        self._attr_device_info = camera.device_info
        self._attr_icon = "mdi:message-text"

        # Build options from NVR custom messages
        self._options_map = {}
        options = []

        # Add standard message types
        for msg_type in LCD_MESSAGE_TYPE_OPTIONS:
            if msg_type != "CUSTOM_MESSAGE":
                label = LCD_MESSAGE_TYPE_LABELS[msg_type]
                options.append(label)
                self._options_map[label] = {"type": msg_type}

        # Add custom messages from NVR
        if coordinator.nvr and coordinator.nvr.doorbell_settings:
            custom_messages = coordinator.nvr.doorbell_settings.get("customMessages", [])
            for custom_msg in custom_messages:
                text = custom_msg.get("text", "")
                if text:
                    options.append(text)
                    self._options_map[text] = {
                        "type": "CUSTOM_MESSAGE",
                        "text": text,
                    }

        self._attr_options = options

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
            and self.camera.is_doorbell
        )

    @property
    def current_option(self) -> str | None:
        """Return the current LCD message."""
        if not self.camera.lcd_message:
            return None

        msg_type = self.camera.lcd_message.get("type")
        msg_text = self.camera.lcd_message.get("text", "")

        if msg_type == "CUSTOM_MESSAGE" and msg_text:
            return msg_text

        return LCD_MESSAGE_TYPE_LABELS.get(msg_type)

    async def async_select_option(self, option: str) -> None:
        """Change the LCD message."""
        if option not in self._options_map:
            _LOGGER.error("Unknown LCD message option: %s", option)
            return

        try:
            msg_data = self._options_map[option]
            lcd_message = {"type": msg_data["type"]}

            if "text" in msg_data:
                lcd_message["text"] = msg_data["text"]

            await self.coordinator.api.update_camera(
                self.camera_id, lcd_message=lcd_message
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting LCD message for %s: %s", self.entity_id, err)
