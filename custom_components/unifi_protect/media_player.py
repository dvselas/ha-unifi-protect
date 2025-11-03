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
        try:
            return float(self.camera.speaker_volume) / 100.0
        except (AttributeError, TypeError, ValueError):
            return None

    @property
    def is_volume_muted(self) -> bool:
        """Return if volume is muted."""
        try:
            return self.camera.speaker_muted
        except AttributeError:
            return False

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level (0..1)."""
        try:
            # Convert volume (0..1) to percentage (0..100)
            volume_percent = int(volume * 100)

            _LOGGER.debug("Setting speaker volume for %s to %d%%", self.camera.name, volume_percent)

            # Update speaker settings
            speaker_settings = {"volume": volume_percent}
            await self.coordinator.api.update_camera(
                self.camera_id, speaker_settings=speaker_settings
            )
            await self.coordinator.async_request_refresh()

            _LOGGER.info("Successfully set speaker volume for %s to %d%%", self.camera.name, volume_percent)

        except Exception as err:
            _LOGGER.error("Error setting volume for %s: %s", self.entity_id, err, exc_info=True)

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
            _LOGGER.debug("%s speaker for %s", "Muting" if mute else "Unmuting", self.camera.name)

            # Update speaker settings with mute state
            # Try areSpeakersMuted field first, fallback to volume=0 for mute
            speaker_settings = {}

            # Some cameras support areSpeakersMuted field
            if "areSpeakersMuted" in self.camera.speaker_settings:
                speaker_settings["areSpeakersMuted"] = mute
            else:
                # Fallback: use volume = 0 for mute, restore previous volume for unmute
                if mute:
                    speaker_settings["volume"] = 0
                else:
                    # Restore to 50% if we don't know the previous volume
                    previous_volume = self.camera.speaker_settings.get("volume", 50)
                    speaker_settings["volume"] = max(previous_volume, 50) if previous_volume == 0 else previous_volume

            await self.coordinator.api.update_camera(
                self.camera_id, speaker_settings=speaker_settings
            )
            await self.coordinator.async_request_refresh()

            _LOGGER.info("Successfully %s speaker for %s", "muted" if mute else "unmuted", self.camera.name)

        except Exception as err:
            _LOGGER.error("Error muting volume for %s: %s", self.entity_id, err, exc_info=True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "camera_id": self.camera_id,
            "has_speaker": self.camera.feature_flags.get("hasSpeaker", False),
            "model": self.camera.model,
            "speaker_volume": self.camera.speaker_volume,
            "speaker_enabled": self.camera.is_speaker_enabled,
        }

        # Add speaker settings for debugging
        if self.camera.speaker_settings:
            attrs["speaker_settings"] = self.camera.speaker_settings

        return attrs
