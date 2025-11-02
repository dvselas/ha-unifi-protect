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
from .models import ProtectCamera, ProtectChime

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
        if camera.feature_flags.get("hasMic") and camera.is_mic_enabled:
            entities.append(CameraMicVolumeNumber(coordinator, camera_id, camera))

    # Add chime volume control for each camera paired to a chime
    for chime_id, chime in coordinator.chimes.items():
        for camera_id in chime.camera_ids:
            if camera_id in coordinator.cameras:
                entities.append(
                    ChimeRingVolumeNumber(
                        coordinator, chime_id, chime, camera_id
                    )
                )

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
