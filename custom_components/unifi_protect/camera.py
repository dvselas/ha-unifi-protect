"""Camera platform for UniFi Protect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
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
    """Set up UniFi Protect cameras."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.info("Setting up UniFi Protect camera platform with %d cameras", len(coordinator.cameras))

    # Add all cameras
    entities = [
        ProtectCameraEntity(coordinator, camera_id, camera)
        for camera_id, camera in coordinator.cameras.items()
    ]

    if entities:
        _LOGGER.debug("Adding %d camera entities", len(entities))
        async_add_entities(entities)
    else:
        _LOGGER.warning("No cameras found to add")


class ProtectCameraEntity(CoordinatorEntity[ProtectDataUpdateCoordinator], Camera):
    """Representation of a UniFi Protect camera."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
    ) -> None:
        """Initialize the camera.

        Args:
            coordinator: The data update coordinator
            camera_id: Camera ID
            camera: Camera data
        """
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)

        self.camera_id = camera_id
        self._attr_unique_id = camera_id
        self._attr_device_info = camera.device_info
        # Set name to None so entity uses device name (not "device_name None")
        self._attr_name = None

    @property
    def camera(self) -> ProtectCamera:
        """Return the camera object."""
        return self.coordinator.cameras[self.camera_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        camera_exists = self.camera_id in self.coordinator.cameras
        is_connected = self.camera.is_connected if camera_exists else False

        available = (
            self.coordinator.last_update_success
            and camera_exists
            and is_connected
        )

        if not available:
            _LOGGER.debug(
                "Camera %s unavailable: last_update_success=%s, exists=%s, connected=%s",
                self.camera_id,
                self.coordinator.last_update_success,
                camera_exists,
                is_connected,
            )

        return available

    @property
    def is_recording(self) -> bool:
        """Return true if the camera is recording."""
        return self.camera.is_recording

    @property
    def is_on(self) -> bool:
        """Return true if the camera is on."""
        return self.camera.is_connected and not self.camera.privacy_mode

    @property
    def motion_detection_enabled(self) -> bool:
        """Return the camera motion detection status."""
        return self.camera.recording_mode in ["motion", "detections", "always"]

    @property
    def brand(self) -> str:
        """Return the camera brand."""
        return "Ubiquiti"

    @property
    def model(self) -> str:
        """Return the camera model."""
        return self.camera.model

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image from the camera.

        Args:
            width: Image width (not used)
            height: Image height (not used)

        Returns:
            Image bytes or None if unavailable
        """
        return await self.coordinator.api.get_camera_snapshot(self.camera_id)

    async def stream_source(self) -> str | None:
        """Return the RTSPS stream source.

        For Integration API v1, we need to create RTSPS streams first,
        then use the returned URL. Stream URLs are cached for 30 minutes.

        Returns:
            RTSPS URL or None if unavailable
        """
        if not self.available:
            _LOGGER.debug("Camera %s not available for streaming", self.camera_id)
            return None

        # Check cache first to avoid repeated API calls
        cached_url = self.coordinator.api.get_cached_stream_url(self.camera_id)
        if cached_url:
            _LOGGER.debug("Using cached stream URL for camera %s", self.camera_id)
            return cached_url

        try:
            # Try to get existing streams first
            _LOGGER.debug("Getting RTSPS streams for camera %s", self.camera_id)
            streams = await self.coordinator.api.get_camera_rtsps_streams(self.camera_id)

            # Check if we have a high quality stream already
            if streams and "high" in streams and streams["high"]:
                stream_url = streams["high"]
                _LOGGER.debug("Using existing RTSPS stream for camera %s", self.camera_id)
                # Cache the URL
                self.coordinator.api.set_cached_stream_url(self.camera_id, stream_url)
                return stream_url

            # No streams exist, create them
            _LOGGER.info("Creating RTSPS streams for camera %s", self.camera_id)
            created_streams = await self.coordinator.api.create_camera_rtsps_streams(
                self.camera_id,
                ["high", "medium", "low"]
            )

            # Return the high quality stream URL
            if created_streams and "high" in created_streams and created_streams["high"]:
                stream_url = created_streams["high"]
                _LOGGER.info("Created RTSPS stream for camera %s", self.camera_id)
                # Cache the URL
                self.coordinator.api.set_cached_stream_url(self.camera_id, stream_url)
                return stream_url

            _LOGGER.warning("No RTSPS stream URL returned for camera %s", self.camera_id)
            return None

        except ConnectionError as err:
            # Rate limit error - return None and let HA retry later
            if "rate limit" in str(err).lower():
                _LOGGER.warning("Rate limit hit for camera %s, will retry later", self.camera_id)
                return None
            _LOGGER.error("Connection error getting stream for camera %s: %s", self.camera_id, err)
            return None
        except Exception as err:
            _LOGGER.error("Error getting stream source for camera %s: %s", self.camera_id, err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes.

        Returns:
            Dictionary of extra attributes
        """
        attrs = {
            "camera_id": self.camera_id,
            "recording_mode": self.camera.recording_mode,
            "privacy_mode": self.camera.privacy_mode,
            "last_motion": self.camera.last_motion,
            "firmware_version": self.camera.firmware_version,
            # V1 API attributes
            "is_mic_enabled": self.camera.is_mic_enabled,
            "mic_volume": self.camera.mic_volume,
            "video_mode": self.camera.video_mode,
            "hdr_type": self.camera.hdr_type,
            "active_patrol_slot": self.camera.active_patrol_slot,
        }

        # Add OSD settings if available
        if self.camera.osd_settings:
            attrs["osd_name_enabled"] = self.camera.osd_settings.get("isNameEnabled")
            attrs["osd_date_enabled"] = self.camera.osd_settings.get("isDateEnabled")
            attrs["osd_logo_enabled"] = self.camera.osd_settings.get("isLogoEnabled")
            attrs["osd_overlay_location"] = self.camera.osd_settings.get("overlayLocation")

        # Add LED settings if available
        if self.camera.led_settings:
            attrs["led_enabled"] = self.camera.led_settings.get("isEnabled")

        # Add LCD message if available (doorbells)
        if self.camera.lcd_message:
            attrs["lcd_message_type"] = self.camera.lcd_message.get("type")
            attrs["lcd_message_text"] = self.camera.lcd_message.get("text")

        # Add feature flags
        if self.camera.feature_flags:
            attrs["supports_hdr"] = self.camera.feature_flags.get("hasHdr", False)
            attrs["has_mic"] = self.camera.feature_flags.get("hasMic", False)
            attrs["has_speaker"] = self.camera.feature_flags.get("hasSpeaker", False)
            attrs["smart_detect_types"] = self.camera.feature_flags.get("smartDetectTypes", [])
            attrs["smart_detect_audio_types"] = self.camera.feature_flags.get("smartDetectAudioTypes", [])

        # Add smart detection settings
        if self.camera.smart_detect_settings:
            attrs["smart_detect_object_types"] = self.camera.smart_detect_settings.get("objectTypes", [])
            attrs["smart_detect_audio_types_enabled"] = self.camera.smart_detect_settings.get("audioTypes", [])

        return attrs
