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
        # Enable streaming support
        self._attr_supported_features = CameraEntityFeature.STREAM
        self._attr_frontend_stream_type = "hls"

    @property
    def camera(self) -> ProtectCamera:
        """Return the camera object."""
        return self.coordinator.cameras[self.camera_id]

    @property
    def supported_features(self) -> int:
        """Return supported features for this camera."""
        return CameraEntityFeature.STREAM

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

        Fetches existing RTSPS stream URLs from the API. These streams
        are automatically created by UniFi Protect and are always available
        for connected cameras.

        Stream URLs are cached for 30 minutes.

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
            # Get existing RTSPS streams from API
            _LOGGER.debug("Fetching RTSPS streams for camera %s", self.camera_id)
            streams = await self.coordinator.api.get_camera_rtsps_streams(self.camera_id)

            if streams:
                # Prefer package stream for fastest loading, fallback to high/medium/low
                stream_url = None
                if streams.get("package"):
                    stream_url = streams["package"]
                    _LOGGER.debug("Using package (fast) RTSPS stream for camera %s", self.camera_id)
                elif streams.get("high"):
                    stream_url = streams["high"]
                    _LOGGER.debug("Using high quality RTSPS stream for camera %s", self.camera_id)
                elif streams.get("medium"):
                    stream_url = streams["medium"]
                    _LOGGER.debug("Using medium quality RTSPS stream for camera %s", self.camera_id)
                elif streams.get("low"):
                    stream_url = streams["low"]
                    _LOGGER.debug("Using low quality RTSPS stream for camera %s", self.camera_id)

                if stream_url:
                    # Cache the URL
                    self.coordinator.api.set_cached_stream_url(self.camera_id, stream_url)
                    return stream_url

            # If no RTSPS streams available, try bootstrap RTSP URL as fallback
            _LOGGER.debug("No RTSPS streams available, trying bootstrap RTSP URL")
            rtsp_url = self.camera.rtsp_url
            if rtsp_url:
                _LOGGER.info("Using bootstrap RTSP URL for camera %s: %s", self.camera.name, rtsp_url)
                self.coordinator.api.set_cached_stream_url(self.camera_id, rtsp_url)
                return rtsp_url

            _LOGGER.error("No stream URL available for camera %s", self.camera_id)
            return None

        except Exception as err:
            _LOGGER.warning("Error fetching RTSPS streams for camera %s: %s", self.camera_id, err)
            # Try bootstrap RTSP URL as fallback
            rtsp_url = self.camera.rtsp_url
            if rtsp_url:
                _LOGGER.info("Using bootstrap RTSP URL as fallback for camera %s", self.camera.name)
                self.coordinator.api.set_cached_stream_url(self.camera_id, rtsp_url)
                return rtsp_url
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
