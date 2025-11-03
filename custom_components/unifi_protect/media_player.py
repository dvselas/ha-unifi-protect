"""Media player platform for UniFi Protect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect media player entities."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[MediaPlayerEntity] = []

    # Add media player for cameras with speakers
    for camera_id, camera in coordinator.cameras.items():
        if camera.feature_flags.get("hasSpeaker"):
            entities.append(ProtectMediaPlayer(coordinator, camera_id, camera))

    if entities:
        async_add_entities(entities)


class ProtectMediaPlayer(CoordinatorEntity[ProtectDataUpdateCoordinator], MediaPlayerEntity):
    """Media player entity for UniFi Protect camera speakers."""

    _attr_has_entity_name = True
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
    )

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
    ) -> None:
        """Initialize the media player.

        Args:
            coordinator: The data update coordinator
            camera_id: Camera ID
            camera: Camera data
        """
        super().__init__(coordinator)
        self.camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_speaker"
        self._attr_name = "Speaker"
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
            and self.camera.feature_flags.get("hasSpeaker", False)
        )

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the media player."""
        if not self.available:
            return MediaPlayerState.OFF

        # Media player is considered "idle" when available
        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        """Return the volume level (0..1)."""
        # Check if camera has speaker_volume field (might be in raw data)
        if hasattr(self.camera, "speaker_volume") and self.camera.speaker_volume is not None:
            return float(self.camera.speaker_volume) / 100.0

        # Default to None if no volume info available
        return None

    @property
    def is_volume_muted(self) -> bool:
        """Return if volume is muted."""
        # Check if camera has speaker_muted field
        if hasattr(self.camera, "speaker_muted"):
            return self.camera.speaker_muted

        # Default to not muted
        return False

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level (0..1)."""
        try:
            # Convert volume (0..1) to percentage (0..100)
            volume_percent = int(volume * 100)

            # Note: This would require an API method to set speaker volume
            # For now, log that the feature is not yet implemented
            _LOGGER.warning(
                "Speaker volume control for %s not yet implemented in Integration API v1",
                self.entity_id
            )

            # Placeholder for when API supports it:
            # await self.coordinator.api.update_camera(
            #     self.camera_id, speaker_volume=volume_percent
            # )
            # await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error setting volume for %s: %s", self.entity_id, err)

    async def async_volume_up(self) -> None:
        """Turn volume up."""
        current_volume = self.volume_level or 0.5
        new_volume = min(1.0, current_volume + 0.1)
        await self.async_set_volume_level(new_volume)

    async def async_volume_down(self) -> None:
        """Turn volume down."""
        current_volume = self.volume_level or 0.5
        new_volume = max(0.0, current_volume - 0.1)
        await self.async_set_volume_level(new_volume)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        try:
            # Note: This would require an API method to mute speaker
            # For now, log that the feature is not yet implemented
            _LOGGER.warning(
                "Speaker mute control for %s not yet implemented in Integration API v1",
                self.entity_id
            )

            # Placeholder for when API supports it:
            # await self.coordinator.api.update_camera(
            #     self.camera_id, speaker_muted=mute
            # )
            # await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error muting volume for %s: %s", self.entity_id, err)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "camera_id": self.camera_id,
            "has_speaker": self.camera.feature_flags.get("hasSpeaker", False),
            "model": self.camera.model,
        }
