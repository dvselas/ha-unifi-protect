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
from .models import ProtectCamera, ProtectLight

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
    ProtectSwitchEntityDescription(
        key="status_led",
        name="Status LED",
        icon="mdi:led-on",
        entity_registry_enabled_default=False,
    ),
    ProtectSwitchEntityDescription(
        key="osd_name",
        name="OSD Name",
        icon="mdi:label",
        entity_registry_enabled_default=False,
    ),
    ProtectSwitchEntityDescription(
        key="osd_date",
        name="OSD Date",
        icon="mdi:calendar",
        entity_registry_enabled_default=False,
    ),
    ProtectSwitchEntityDescription(
        key="osd_logo",
        name="OSD Logo",
        icon="mdi:watermark",
        entity_registry_enabled_default=False,
    ),
    ProtectSwitchEntityDescription(
        key="high_fps_mode",
        name="High FPS Mode",
        icon="mdi:video-high-definition",
        entity_registry_enabled_default=False,
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

    # Add status LED switch for each floodlight
    for light_id, light in coordinator.lights.items():
        entities.append(
            ProtectLightStatusLEDSwitch(
                coordinator,
                light_id,
                light,
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
        elif self.entity_description.key == "status_led":
            return self.camera.led_settings.get("isEnabled", False) if self.camera.led_settings else False
        elif self.entity_description.key == "osd_name":
            return self.camera.osd_settings.get("isNameEnabled", False) if self.camera.osd_settings else False
        elif self.entity_description.key == "osd_date":
            return self.camera.osd_settings.get("isDateEnabled", False) if self.camera.osd_settings else False
        elif self.entity_description.key == "osd_logo":
            return self.camera.osd_settings.get("isLogoEnabled", False) if self.camera.osd_settings else False
        elif self.entity_description.key == "high_fps_mode":
            return self.camera.video_mode == "highFps"

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
            elif self.entity_description.key == "status_led":
                led_settings = self.camera.led_settings.copy() if self.camera.led_settings else {}
                led_settings["isEnabled"] = True
                await self.coordinator.api.update_camera(
                    self.camera_id, led_settings=led_settings
                )
            elif self.entity_description.key == "osd_name":
                osd_settings = self.camera.osd_settings.copy() if self.camera.osd_settings else {}
                osd_settings["isNameEnabled"] = True
                await self.coordinator.api.update_camera(
                    self.camera_id, osd_settings=osd_settings
                )
            elif self.entity_description.key == "osd_date":
                osd_settings = self.camera.osd_settings.copy() if self.camera.osd_settings else {}
                osd_settings["isDateEnabled"] = True
                await self.coordinator.api.update_camera(
                    self.camera_id, osd_settings=osd_settings
                )
            elif self.entity_description.key == "osd_logo":
                osd_settings = self.camera.osd_settings.copy() if self.camera.osd_settings else {}
                osd_settings["isLogoEnabled"] = True
                await self.coordinator.api.update_camera(
                    self.camera_id, osd_settings=osd_settings
                )
            elif self.entity_description.key == "high_fps_mode":
                await self.coordinator.api.update_camera(
                    self.camera_id, video_mode="highFps"
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
            elif self.entity_description.key == "status_led":
                led_settings = self.camera.led_settings.copy() if self.camera.led_settings else {}
                led_settings["isEnabled"] = False
                await self.coordinator.api.update_camera(
                    self.camera_id, led_settings=led_settings
                )
            elif self.entity_description.key == "osd_name":
                osd_settings = self.camera.osd_settings.copy() if self.camera.osd_settings else {}
                osd_settings["isNameEnabled"] = False
                await self.coordinator.api.update_camera(
                    self.camera_id, osd_settings=osd_settings
                )
            elif self.entity_description.key == "osd_date":
                osd_settings = self.camera.osd_settings.copy() if self.camera.osd_settings else {}
                osd_settings["isDateEnabled"] = False
                await self.coordinator.api.update_camera(
                    self.camera_id, osd_settings=osd_settings
                )
            elif self.entity_description.key == "osd_logo":
                osd_settings = self.camera.osd_settings.copy() if self.camera.osd_settings else {}
                osd_settings["isLogoEnabled"] = False
                await self.coordinator.api.update_camera(
                    self.camera_id, osd_settings=osd_settings
                )
            elif self.entity_description.key == "high_fps_mode":
                await self.coordinator.api.update_camera(
                    self.camera_id, video_mode="default"
                )

            # Request coordinator update
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error turning off %s: %s", self.entity_id, err)


class ProtectLightStatusLEDSwitch(
    CoordinatorEntity[ProtectDataUpdateCoordinator], SwitchEntity
):
    """Switch entity for floodlight status LED."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:led-on"
    _attr_name = "Status Light"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        light_id: str,
        light: ProtectLight,
    ) -> None:
        """Initialize the switch.

        Args:
            coordinator: The data update coordinator
            light_id: Light ID
            light: Light data
        """
        super().__init__(coordinator)
        self.light_id = light_id
        self._attr_unique_id = f"{light_id}_status_light"
        self._attr_device_info = light.device_info

    @property
    def light(self) -> ProtectLight:
        """Return the light object."""
        return self.coordinator.lights[self.light_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.light_id in self.coordinator.lights
            and self.light.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.light.is_indicator_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            light_device_settings = {"isIndicatorEnabled": True}
            await self.coordinator.api.update_light(
                self.light_id, light_device_settings=light_device_settings
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error turning on %s: %s", self.entity_id, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            light_device_settings = {"isIndicatorEnabled": False}
            await self.coordinator.api.update_light(
                self.light_id, light_device_settings=light_device_settings
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error turning off %s: %s", self.entity_id, err)
