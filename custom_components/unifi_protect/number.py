"""Number platform for UniFi Protect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera, ProtectChime, ProtectLight

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect number entities."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NumberEntity] = []

    # Add microphone volume control for each camera with a microphone
    for camera_id, camera in coordinator.cameras.items():
        if camera.has_microphone and camera.is_mic_enabled:
            entities.append(CameraMicVolumeNumber(coordinator, camera_id, camera))

        # Add WDR level control for cameras that support it
        if camera.wdr_value is not None:
            entities.append(CameraWDRNumber(coordinator, camera_id, camera))

        # Add zoom control for cameras with PTZ capability
        if camera.zoom_position is not None:
            entities.append(CameraZoomNumber(coordinator, camera_id, camera))

    # Add chime volume control for each camera paired to a chime
    for chime_id, chime in coordinator.chimes.items():
        for camera_id in chime.camera_ids:
            if camera_id in coordinator.cameras:
                entities.append(
                    ChimeRingVolumeNumber(
                        coordinator, chime_id, chime, camera_id
                    )
                )

    # Add floodlight controls
    for light_id, light in coordinator.lights.items():
        # PIR sensitivity control
        entities.append(LightPIRSensitivityNumber(coordinator, light_id, light))
        # Auto-shutoff duration control
        entities.append(LightPIRDurationNumber(coordinator, light_id, light))

    async_add_entities(entities)


class CameraMicVolumeNumber(CoordinatorEntity[ProtectDataUpdateCoordinator], NumberEntity):
    """Number entity for camera microphone volume."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:microphone"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_mic_volume"
        self._attr_name = "Microphone Volume"
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
            and self.camera.is_mic_enabled
        )

    @property
    def native_value(self) -> float:
        """Return the current microphone volume."""
        return float(self.camera.mic_volume)

    async def async_set_native_value(self, value: float) -> None:
        """Set the microphone volume."""
        try:
            await self.coordinator.api.update_camera(
                self.camera_id, mic_volume=int(value)
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting mic volume for %s: %s", self.entity_id, err)


class CameraWDRNumber(CoordinatorEntity[ProtectDataUpdateCoordinator], NumberEntity):
    """Number entity for camera WDR level."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 3
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:weather-sunny"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_wdr_level"
        self._attr_name = "WDR Level"
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
            and self.camera.wdr_value is not None
        )

    @property
    def native_value(self) -> float:
        """Return the current WDR level."""
        return float(self.camera.wdr_value) if self.camera.wdr_value is not None else 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the WDR level."""
        try:
            await self.coordinator.api.update_camera(
                self.camera_id, wdr_value=int(value)
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting WDR level for %s: %s", self.entity_id, err)


class CameraZoomNumber(CoordinatorEntity[ProtectDataUpdateCoordinator], NumberEntity):
    """Number entity for camera zoom position."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:magnify"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_zoom_position"
        self._attr_name = "Zoom Position"
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
            and self.camera.zoom_position is not None
        )

    @property
    def native_value(self) -> float:
        """Return the current zoom position."""
        return float(self.camera.zoom_position) if self.camera.zoom_position is not None else 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the zoom position."""
        try:
            await self.coordinator.api.update_camera(
                self.camera_id, zoom_position=int(value)
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting zoom position for %s: %s", self.entity_id, err)


class ChimeRingVolumeNumber(CoordinatorEntity[ProtectDataUpdateCoordinator], NumberEntity):
    """Number entity for chime ring volume per camera."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:bell-ring"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        chime_id: str,
        chime: ProtectChime,
        camera_id: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.chime_id = chime_id
        self.camera_id = camera_id
        self._attr_unique_id = f"{chime_id}_volume_{camera_id}"
        self._attr_device_info = chime.device_info

        # Set name based on camera
        camera_name = "Unknown"
        if camera_id in coordinator.cameras:
            camera_name = coordinator.cameras[camera_id].name or camera_id
        self._attr_name = f"{camera_name} Ring Volume"

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
            and self.camera_id in self.chime.camera_ids
        )

    @property
    def native_value(self) -> float:
        """Return the current ring volume for this camera."""
        ring_setting = self.chime.get_ring_setting_for_camera(self.camera_id)
        if ring_setting:
            return float(ring_setting.get("volume", 100))
        return 100.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the ring volume for this camera."""
        try:
            # Get existing ring settings
            ring_settings = []
            for setting in self.chime.ring_settings:
                if setting.get("cameraId") == self.camera_id:
                    # Update this camera's volume
                    updated_setting = setting.copy()
                    updated_setting["volume"] = int(value)
                    ring_settings.append(updated_setting)
                else:
                    # Keep other cameras' settings unchanged
                    ring_settings.append(setting)

            # If camera not in ring settings, add it with new volume
            if not any(s.get("cameraId") == self.camera_id for s in ring_settings):
                ring_settings.append({
                    "cameraId": self.camera_id,
                    "volume": int(value),
                    "repeatTimes": 1,
                    "ringtoneId": "",
                })

            await self.coordinator.api.update_chime(
                self.chime_id, ring_settings=ring_settings
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting chime ring volume for %s: %s", self.entity_id, err)


class LightPIRSensitivityNumber(CoordinatorEntity[ProtectDataUpdateCoordinator], NumberEntity):
    """Number entity for floodlight PIR motion sensitivity."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:motion-sensor"
    _attr_name = "PIR Motion Sensitivity"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        light_id: str,
        light: ProtectLight,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.light_id = light_id
        self._attr_unique_id = f"{light_id}_pir_sensitivity"
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
    def native_value(self) -> float:
        """Return the current PIR sensitivity."""
        return float(self.light.pir_sensitivity)

    async def async_set_native_value(self, value: float) -> None:
        """Set the PIR sensitivity."""
        try:
            light_device_settings = {"pirSensitivity": int(value)}
            await self.coordinator.api.update_light(
                self.light_id, light_device_settings=light_device_settings
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting PIR sensitivity for %s: %s", self.entity_id, err)


class LightPIRDurationNumber(CoordinatorEntity[ProtectDataUpdateCoordinator], NumberEntity):
    """Number entity for floodlight auto-shutoff duration."""

    _attr_has_entity_name = True
    _attr_native_min_value = 15
    _attr_native_max_value = 300
    _attr_native_step = 15
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:timer"
    _attr_name = "Auto-shutoff Duration"
    _attr_native_unit_of_measurement = "s"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        light_id: str,
        light: ProtectLight,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.light_id = light_id
        self._attr_unique_id = f"{light_id}_pir_duration"
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
    def native_value(self) -> float:
        """Return the current auto-shutoff duration in seconds."""
        # Convert milliseconds to seconds
        return float(self.light.pir_duration / 1000)

    async def async_set_native_value(self, value: float) -> None:
        """Set the auto-shutoff duration."""
        try:
            # Convert seconds to milliseconds
            duration_ms = int(value * 1000)
            light_device_settings = {"pirDuration": duration_ms}
            await self.coordinator.api.update_light(
                self.light_id, light_device_settings=light_device_settings
            )
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error setting auto-shutoff duration for %s: %s", self.entity_id, err)
