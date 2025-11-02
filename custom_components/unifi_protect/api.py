"""UniFi Protect API Client for v6.1.79+."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType

_LOGGER = logging.getLogger(__name__)


class ProtectAPIError(Exception):
    """Base exception for Protect API errors."""


class AuthenticationError(ProtectAPIError):
    """Authentication failed."""


class ConnectionError(ProtectAPIError):
    """Connection to Protect failed."""


class UniFiProtectAPI:
    """API client for UniFi Protect v6+."""

    def __init__(
        self,
        host: str,
        api_token: str,
        session: ClientSession | None = None,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the API client.

        Args:
            host: The hostname/IP of the UniFi Protect server
            api_token: API token generated in Protect UI
            session: Optional aiohttp ClientSession
            verify_ssl: Whether to verify SSL certificates
        """
        self.host = host.rstrip("/")
        self._api_token = api_token
        self._session = session
        self._own_session = session is None
        self._verify_ssl = verify_ssl
        self._ws_devices: ClientWebSocketResponse | None = None
        self._ws_events: ClientWebSocketResponse | None = None
        self._ws_devices_task: asyncio.Task | None = None
        self._ws_events_task: asyncio.Task | None = None
        self._ws_device_callbacks: list[Callable] = []
        self._ws_event_callbacks: list[Callable] = []

        # Ensure host has protocol
        if not self.host.startswith(("http://", "https://")):
            self.host = f"https://{self.host}"

    @property
    def _headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        return {
            "X-API-KEY": self._api_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self._verify_ssl)
            )
        return self._session

    async def close(self) -> None:
        """Close the API connection."""
        await self.disconnect_websocket()

        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Make an API request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (e.g., "/api/bootstrap")
            **kwargs: Additional arguments passed to aiohttp request

        Returns:
            JSON response data

        Raises:
            AuthenticationError: If authentication fails
            ConnectionError: If connection fails
            ProtectAPIError: For other API errors
        """
        url = urljoin(self.host, endpoint)
        session = await self._get_session()

        try:
            async with session.request(
                method,
                url,
                headers=self._headers,
                **kwargs,
            ) as response:
                if response.status == 401:
                    raise AuthenticationError("Invalid API token")

                if response.status == 403:
                    raise AuthenticationError("Insufficient permissions")

                response.raise_for_status()

                # Handle empty responses
                if response.status == 204:
                    return {}

                return await response.json()

        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error: %s", err)
            raise ConnectionError(f"Failed to connect to {self.host}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err)
            raise ProtectAPIError(f"API request failed: {err}") from err

    async def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Make a GET request."""
        return await self.request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Make a POST request."""
        return await self.request("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Make a PUT request."""
        return await self.request("PUT", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Make a PATCH request."""
        return await self.request("PATCH", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Make a DELETE request."""
        return await self.request("DELETE", endpoint, **kwargs)

    async def get_application_info(self) -> dict[str, Any]:
        """Get application information.

        Returns:
            Application info with version information (includes injected host field)

        Raises:
            AuthenticationError: If authentication fails
            ConnectionError: If connection fails
        """
        data = await self.get("/proxy/protect/integration/v1/meta/info")
        # Inject host information since API doesn't return it
        if isinstance(data, dict):
            data["host"] = self.host
        return data

    # NVR methods

    async def get_nvr_v1(self) -> dict[str, Any]:
        """Get NVR details using v1 API.

        Returns:
            Detailed NVR data including doorbell settings (includes injected host field)

        Raises:
            AuthenticationError: If authentication fails
            ConnectionError: If connection fails
        """
        data = await self.get("/proxy/protect/integration/v1/nvr")
        # Inject host information since API doesn't return it
        if isinstance(data, dict):
            data["host"] = self.host
        return data

    # Device asset file management methods

    async def upload_asset_file(
        self,
        file_type: str,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> dict[str, Any]:
        """Upload a device asset file.

        Args:
            file_type: Asset file type (currently only "animations" is supported)
            file_data: Binary file data
            filename: Original filename
            content_type: MIME type (image/gif, image/jpeg, image/png, audio/mpeg, audio/mp4, audio/wave, audio/x-caf)

        Returns:
            Asset file info with name, type, originalName, path

        Raises:
            ValueError: If file_type is not supported
        """
        if file_type not in ["animations"]:
            raise ValueError(f"Unsupported file type: {file_type}. Only 'animations' is currently supported.")

        session = await self._get_session()
        url = urljoin(self.host, f"/proxy/protect/integration/v1/files/{file_type}")

        # Create multipart form data
        form_data = aiohttp.FormData()
        form_data.add_field(
            "file",
            file_data,
            filename=filename,
            content_type=content_type,
        )

        try:
            async with session.post(
                url,
                headers={"X-API-KEY": self._api_token},  # Don't include Content-Type, aiohttp sets it
                data=form_data,
            ) as response:
                if response.status == 401:
                    raise AuthenticationError("Invalid API token")
                if response.status == 403:
                    raise AuthenticationError("Insufficient permissions")

                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error uploading asset: %s", err)
            raise ConnectionError(f"Failed to upload asset file: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error uploading asset: %s", err)
            raise ProtectAPIError(f"Asset upload failed: {err}") from err

    async def get_asset_files(self, file_type: str = "animations") -> list[dict[str, Any]]:
        """Get list of all device asset files.

        Args:
            file_type: Asset file type (currently only "animations" is supported)

        Returns:
            List of asset file info with name, type, originalName, path

        Raises:
            ValueError: If file_type is not supported
        """
        if file_type not in ["animations"]:
            raise ValueError(f"Unsupported file type: {file_type}. Only 'animations' is currently supported.")

        return await self.get(f"/proxy/protect/integration/v1/files/{file_type}")

    # Chime methods

    async def get_chimes(self) -> list[dict[str, Any]]:
        """Get all chimes.

        Returns:
            List of chime data
        """
        return await self.get("/proxy/protect/integration/v1/chimes")

    async def get_chime(self, chime_id: str) -> dict[str, Any]:
        """Get specific chime details.

        Args:
            chime_id: Chime UUID

        Returns:
            Chime data
        """
        return await self.get(f"/proxy/protect/integration/v1/chimes/{chime_id}")

    async def update_chime(
        self,
        chime_id: str,
        name: str | None = None,
        camera_ids: list[str] | None = None,
        ring_settings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update chime settings.

        Args:
            chime_id: Chime UUID
            name: Chime name
            camera_ids: List of doorbell camera IDs paired to this chime
            ring_settings: List of custom ringtone settings per camera
                Each setting contains:
                - cameraId: Camera UUID
                - repeatTimes: How many times to repeat (1-10)
                - ringtoneId: ID of ringtone to play
                - volume: Volume level (0-100)

        Returns:
            Updated chime data
        """
        data = {}
        if name is not None:
            data["name"] = name
        if camera_ids is not None:
            data["cameraIds"] = camera_ids
        if ring_settings is not None:
            data["ringSettings"] = ring_settings

        return await self.patch(
            f"/proxy/protect/integration/v1/chimes/{chime_id}",
            json=data,
        )

    # Viewer methods

    async def get_viewers(self) -> list[dict[str, Any]]:
        """Get all viewers.

        Returns:
            List of viewer data
        """
        return await self.get("/proxy/protect/integration/v1/viewers")

    async def get_viewer(self, viewer_id: str) -> dict[str, Any]:
        """Get specific viewer data.

        Args:
            viewer_id: Viewer UUID

        Returns:
            Viewer data
        """
        return await self.get(f"/proxy/protect/integration/v1/viewers/{viewer_id}")

    async def update_viewer(
        self,
        viewer_id: str,
        name: str | None = None,
        liveview: str | None = None,
    ) -> dict[str, Any]:
        """Update viewer settings.

        Args:
            viewer_id: Viewer UUID
            name: New name for the viewer
            liveview: Liveview ID to assign to the viewer

        Returns:
            Updated viewer data
        """
        data = {}
        if name is not None:
            data["name"] = name
        if liveview is not None:
            data["liveview"] = liveview

        return await self.patch(f"/proxy/protect/integration/v1/viewers/{viewer_id}", json=data)

    # Liveview methods

    async def get_liveviews(self) -> list[dict[str, Any]]:
        """Get all liveviews.

        Returns:
            List of liveview data
        """
        return await self.get("/proxy/protect/integration/v1/liveviews")

    async def get_liveview(self, liveview_id: str) -> dict[str, Any]:
        """Get specific liveview data.

        Args:
            liveview_id: Liveview UUID

        Returns:
            Liveview data
        """
        return await self.get(f"/proxy/protect/integration/v1/liveviews/{liveview_id}")

    async def create_liveview(self, liveview_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new liveview.

        Args:
            liveview_data: Liveview configuration data

        Returns:
            Created liveview data
        """
        return await self.post("/proxy/protect/integration/v1/liveviews", json=liveview_data)

    async def update_liveview(
        self, liveview_id: str, liveview_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update liveview configuration.

        Args:
            liveview_id: Liveview UUID
            liveview_data: Updated liveview configuration

        Returns:
            Updated liveview data
        """
        return await self.patch(f"/proxy/protect/integration/v1/liveviews/{liveview_id}", json=liveview_data)

    async def verify_connection(self) -> bool:
        """Verify the connection and authentication.

        Returns:
            True if connection and authentication successful

        Raises:
            AuthenticationError: If authentication fails
            ConnectionError: If connection fails
        """
        try:
            # Try to get application info to verify connection
            await self.get_application_info()
            return True
        except (AuthenticationError, ConnectionError):
            raise
        except Exception as err:
            _LOGGER.error("Failed to verify connection: %s", err)
            return False

    async def get_bootstrap(self) -> dict[str, Any]:
        """Get bootstrap data containing all devices and settings.

        Returns:
            Bootstrap data with all cameras, sensors, and configuration (includes injected host field in nvr data)
        """
        data = await self.get("/proxy/protect/api/bootstrap")
        # Inject host information into NVR data since API doesn't return it
        if isinstance(data, dict) and "nvr" in data and isinstance(data["nvr"], dict):
            data["nvr"]["host"] = self.host
        return data

    async def get_cameras(self) -> list[dict[str, Any]]:
        """Get all cameras.

        Returns:
            List of camera data
        """
        bootstrap = await self.get_bootstrap()
        return bootstrap.get("cameras", [])

    async def get_camera(self, camera_id: str) -> dict[str, Any]:
        """Get specific camera data.

        Args:
            camera_id: Camera UUID

        Returns:
            Camera data
        """
        return await self.get(f"/proxy/protect/api/cameras/{camera_id}")

    async def set_recording_mode(
        self, camera_id: str, mode: str
    ) -> dict[str, Any]:
        """Set camera recording mode.

        Args:
            camera_id: Camera UUID
            mode: Recording mode (always, never, motion, detections)

        Returns:
            Updated camera data
        """
        return await self.patch(
            f"/proxy/protect/api/cameras/{camera_id}",
            json={"recordingSettings": {"mode": mode}},
        )

    async def set_privacy_mode(
        self, camera_id: str, enabled: bool
    ) -> dict[str, Any]:
        """Enable/disable privacy mode on camera.

        Args:
            camera_id: Camera UUID
            enabled: Privacy mode state

        Returns:
            Updated camera data
        """
        return await self.patch(
            f"/proxy/protect/api/cameras/{camera_id}",
            json={"privacyModeEnabled": enabled},
        )

    # V1 Camera API methods

    async def get_cameras_v1(self) -> list[dict[str, Any]]:
        """Get all cameras using v1 API.

        Returns:
            List of detailed camera data
        """
        return await self.get("/proxy/protect/integration/v1/cameras")

    async def get_camera_v1(self, camera_id: str) -> dict[str, Any]:
        """Get specific camera details using v1 API.

        Args:
            camera_id: Camera UUID

        Returns:
            Detailed camera data
        """
        return await self.get(f"/proxy/protect/integration/v1/cameras/{camera_id}")

    async def update_camera(
        self,
        camera_id: str,
        name: str | None = None,
        osd_settings: dict[str, Any] | None = None,
        led_settings: dict[str, Any] | None = None,
        lcd_message: dict[str, Any] | None = None,
        mic_volume: int | None = None,
        video_mode: str | None = None,
        hdr_type: str | None = None,
        smart_detect_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update camera settings using v1 API.

        Args:
            camera_id: Camera UUID
            name: Camera name
            osd_settings: On Screen Display settings (isNameEnabled, isDateEnabled, isLogoEnabled, isDebugEnabled, overlayLocation)
            led_settings: LED settings (isEnabled)
            lcd_message: LCD doorbell message (type, resetAt, text)
            mic_volume: Microphone volume (0-100)
            video_mode: Video mode (default, highFps, sport, slowShutter, lprReflex, lprNoneReflex)
            hdr_type: HDR mode (auto, on, off)
            smart_detect_settings: Smart detection settings (objectTypes, audioTypes)

        Returns:
            Updated camera data
        """
        data = {}
        if name is not None:
            data["name"] = name
        if osd_settings is not None:
            data["osdSettings"] = osd_settings
        if led_settings is not None:
            data["ledSettings"] = led_settings
        if lcd_message is not None:
            data["lcdMessage"] = lcd_message
        if mic_volume is not None:
            if not 0 <= mic_volume <= 100:
                raise ValueError("Mic volume must be between 0 and 100")
            data["micVolume"] = mic_volume
        if video_mode is not None:
            data["videoMode"] = video_mode
        if hdr_type is not None:
            data["hdrType"] = hdr_type
        if smart_detect_settings is not None:
            data["smartDetectSettings"] = smart_detect_settings

        return await self.patch(
            f"/proxy/protect/integration/v1/cameras/{camera_id}",
            json=data,
        )

    async def create_camera_rtsps_streams(
        self, camera_id: str, qualities: list[str]
    ) -> dict[str, str]:
        """Create RTSPS streams for camera.

        Args:
            camera_id: Camera UUID
            qualities: List of quality levels (high, medium, low, package)

        Returns:
            Dictionary mapping quality to RTSPS URL

        Example:
            {"high": "rtsps://192.168.1.1:7441/token?enableSrtp"}
        """
        return await self.post(
            f"/proxy/protect/integration/v1/cameras/{camera_id}/rtsps-stream",
            json={"qualities": qualities},
        )

    async def get_camera_rtsps_streams(
        self, camera_id: str
    ) -> dict[str, str | None]:
        """Get existing RTSPS streams for camera.

        Args:
            camera_id: Camera UUID

        Returns:
            Dictionary with quality levels and their RTSPS URLs (or None if not created)
        """
        return await self.get(
            f"/proxy/protect/integration/v1/cameras/{camera_id}/rtsps-stream"
        )

    async def delete_camera_rtsps_streams(
        self, camera_id: str, qualities: list[str]
    ) -> None:
        """Delete RTSPS streams for camera.

        Args:
            camera_id: Camera UUID
            qualities: List of quality levels to remove (high, medium, low, package)
        """
        # Build query string
        query_params = "&".join(f"qualities={q}" for q in qualities)
        await self.delete(
            f"/proxy/protect/integration/v1/cameras/{camera_id}/rtsps-stream?{query_params}"
        )

    async def get_camera_snapshot_v1(
        self, camera_id: str, high_quality: bool = False
    ) -> bytes:
        """Get camera snapshot image using v1 API.

        Args:
            camera_id: Camera UUID
            high_quality: Whether to force 1080P or higher resolution

        Returns:
            JPEG image data as bytes
        """
        params = {"highQuality": "true" if high_quality else "false"}
        session = await self._get_session()
        url = urljoin(self.host, f"/proxy/protect/integration/v1/cameras/{camera_id}/snapshot")

        async with session.get(
            url, headers=self._headers, params=params
        ) as response:
            response.raise_for_status()
            return await response.read()

    async def disable_camera_microphone_permanently(
        self, camera_id: str
    ) -> dict[str, Any]:
        """Permanently disable camera microphone.

        WARNING: This action cannot be undone unless the camera is factory reset.

        Args:
            camera_id: Camera UUID

        Returns:
            Updated camera data
        """
        return await self.post(
            f"/proxy/protect/integration/v1/cameras/{camera_id}/disable-mic-permanently"
        )

    async def create_talkback_session(self, camera_id: str) -> dict[str, Any]:
        """Create talkback session for camera.

        Args:
            camera_id: Camera UUID

        Returns:
            Talkback configuration with url, codec, samplingRate, bitsPerSample
        """
        return await self.post(
            f"/proxy/protect/integration/v1/cameras/{camera_id}/talkback-session"
        )

    # PTZ Camera control methods

    async def ptz_start_patrol(self, camera_id: str, slot: int) -> None:
        """Start a PTZ camera patrol.

        Args:
            camera_id: Camera UUID
            slot: Patrol slot number (0-4)

        Raises:
            ValueError: If slot is not between 0-4
        """
        if not 0 <= slot <= 4:
            raise ValueError("Patrol slot must be between 0 and 4")

        await self.post(
            f"/proxy/protect/integration/v1/cameras/{camera_id}/ptz/patrol/start/{slot}"
        )

    async def ptz_stop_patrol(self, camera_id: str) -> None:
        """Stop active PTZ camera patrol.

        Args:
            camera_id: Camera UUID
        """
        await self.post(
            f"/proxy/protect/integration/v1/cameras/{camera_id}/ptz/patrol/stop"
        )

    async def ptz_goto_preset(self, camera_id: str, slot: int) -> None:
        """Move PTZ camera to a preset position.

        Args:
            camera_id: Camera UUID
            slot: Preset slot number (-1 for home position, 0+ for presets)
        """
        await self.post(
            f"/proxy/protect/integration/v1/cameras/{camera_id}/ptz/goto/{slot}"
        )

    # Sensor methods

    async def get_sensors_v1(self) -> list[dict[str, Any]]:
        """Get all sensors using v1 API.

        Returns:
            List of detailed sensor data
        """
        return await self.get("/proxy/protect/integration/v1/sensors")

    async def get_sensor_v1(self, sensor_id: str) -> dict[str, Any]:
        """Get specific sensor details using v1 API.

        Args:
            sensor_id: Sensor UUID

        Returns:
            Detailed sensor data
        """
        return await self.get(f"/proxy/protect/integration/v1/sensors/{sensor_id}")

    async def update_sensor(
        self,
        sensor_id: str,
        name: str | None = None,
        light_settings: dict[str, Any] | None = None,
        humidity_settings: dict[str, Any] | None = None,
        temperature_settings: dict[str, Any] | None = None,
        motion_settings: dict[str, Any] | None = None,
        alarm_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update sensor settings using v1 API.

        Args:
            sensor_id: Sensor UUID
            name: Sensor name
            light_settings: Light sensor settings (isEnabled, lowThreshold, highThreshold)
            humidity_settings: Humidity sensor settings (isEnabled, lowThreshold, highThreshold)
            temperature_settings: Temperature sensor settings (isEnabled, lowThreshold, highThreshold)
            motion_settings: Motion sensor settings (isEnabled, sensitivity 0-100)
            alarm_settings: Alarm sensor settings (isEnabled)

        Returns:
            Updated sensor data
        """
        data = {}
        if name is not None:
            data["name"] = name
        if light_settings is not None:
            data["lightSettings"] = light_settings
        if humidity_settings is not None:
            data["humiditySettings"] = humidity_settings
        if temperature_settings is not None:
            data["temperatureSettings"] = temperature_settings
        if motion_settings is not None:
            data["motionSettings"] = motion_settings
        if alarm_settings is not None:
            data["alarmSettings"] = alarm_settings

        return await self.patch(
            f"/proxy/protect/integration/v1/sensors/{sensor_id}",
            json=data,
        )

    # Light methods

    async def get_lights(self) -> list[dict[str, Any]]:
        """Get all lights.

        Returns:
            List of light data
        """
        return await self.get("/proxy/protect/integration/v1/lights")

    async def get_light(self, light_id: str) -> dict[str, Any]:
        """Get specific light data.

        Args:
            light_id: Light UUID

        Returns:
            Light data
        """
        return await self.get(f"/proxy/protect/integration/v1/lights/{light_id}")

    async def update_light(
        self,
        light_id: str,
        name: str | None = None,
        is_light_force_enabled: bool | None = None,
        light_mode_settings: dict[str, Any] | None = None,
        light_device_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update light settings.

        Args:
            light_id: Light UUID
            name: New name for the light
            is_light_force_enabled: Force enable/disable the light
            light_mode_settings: Light mode settings (mode, enableAt)
            light_device_settings: Device settings (brightness, sensitivity, etc.)

        Returns:
            Updated light data
        """
        data = {}
        if name is not None:
            data["name"] = name
        if is_light_force_enabled is not None:
            data["isLightForceEnabled"] = is_light_force_enabled
        if light_mode_settings is not None:
            data["lightModeSettings"] = light_mode_settings
        if light_device_settings is not None:
            data["lightDeviceSettings"] = light_device_settings

        return await self.patch(f"/proxy/protect/integration/v1/lights/{light_id}", json=data)

    async def set_light_brightness(self, light_id: str, brightness: int) -> dict[str, Any]:
        """Set light brightness level.

        Args:
            light_id: Light UUID
            brightness: Brightness level (1-6)

        Returns:
            Updated light data

        Raises:
            ValueError: If brightness is not between 1-6
        """
        if not 1 <= brightness <= 6:
            raise ValueError("Brightness must be between 1 and 6")

        return await self.update_light(
            light_id,
            light_device_settings={"ledLevel": brightness},
        )

    # Alarm manager methods

    async def trigger_alarm(self, trigger_id: str) -> None:
        """Trigger an alarm via webhook.

        Sends a webhook to the alarm manager to trigger configured alarms
        that match the specified trigger ID.

        Args:
            trigger_id: User-defined string to trigger specific alarms.
                       Alarms must be configured with the same ID to be triggered.

        Raises:
            ProtectAPIError: If the trigger ID is invalid or alarm trigger fails
        """
        await self.post(
            f"/proxy/protect/integration/v1/alarm-manager/webhook/{trigger_id}"
        )

    def get_camera_snapshot_url(self, camera_id: str) -> str:
        """Get URL for camera snapshot.

        Args:
            camera_id: Camera UUID

        Returns:
            Snapshot URL
        """
        return urljoin(self.host, f"/proxy/protect/api/cameras/{camera_id}/snapshot")

    async def get_camera_snapshot(self, camera_id: str) -> bytes | None:
        """Get camera snapshot image bytes.

        Args:
            camera_id: Camera UUID

        Returns:
            Image bytes or None if unavailable
        """
        try:
            url = self.get_camera_snapshot_url(camera_id)
            session = await self._get_session()

            async with session.get(url, headers=self._headers) as response:
                if response.status == 200:
                    return await response.read()

                _LOGGER.error("Error getting camera snapshot: HTTP %s", response.status)
                return None

        except Exception as err:
            _LOGGER.error("Error getting camera snapshot: %s", err)
            return None

    def get_camera_stream_url(self, camera_id: str, channel: int = 0) -> str:
        """Get RTSP stream URL for camera.

        Args:
            camera_id: Camera UUID
            channel: Stream channel (0=high, 1=medium, 2=low)

        Returns:
            RTSPS stream URL for UniFi Protect v6
        """
        # Extract hostname/IP without protocol
        host_only = self.host.replace("https://", "").replace("http://", "")
        # Use RTSPS (secure RTSP) on port 7441 for UniFi Protect v6
        return f"rtsps://{host_only}:7441/{camera_id}_{channel}"

    # WebSocket methods

    def register_device_callback(self, callback: Callable) -> None:
        """Register a callback for device WebSocket updates.

        Args:
            callback: Async function to call with device update data
        """
        if callback not in self._ws_device_callbacks:
            self._ws_device_callbacks.append(callback)

    def unregister_device_callback(self, callback: Callable) -> None:
        """Unregister a device WebSocket callback.

        Args:
            callback: Callback to remove
        """
        if callback in self._ws_device_callbacks:
            self._ws_device_callbacks.remove(callback)

    def register_event_callback(self, callback: Callable) -> None:
        """Register a callback for event WebSocket updates.

        Args:
            callback: Async function to call with event data
        """
        if callback not in self._ws_event_callbacks:
            self._ws_event_callbacks.append(callback)

    def unregister_event_callback(self, callback: Callable) -> None:
        """Unregister an event WebSocket callback.

        Args:
            callback: Callback to remove
        """
        if callback in self._ws_event_callbacks:
            self._ws_event_callbacks.remove(callback)

    async def connect_websocket(self) -> None:
        """Connect to WebSocket subscriptions for real-time updates."""
        if self._ws_devices_task is None:
            self._ws_devices_task = asyncio.create_task(
                self._websocket_loop("/proxy/protect/integration/v1/subscribe/devices", "devices")
            )
            _LOGGER.info("Device WebSocket connection started")

        if self._ws_events_task is None:
            self._ws_events_task = asyncio.create_task(
                self._websocket_loop("/proxy/protect/integration/v1/subscribe/events", "events")
            )
            _LOGGER.info("Events WebSocket connection started")

    async def disconnect_websocket(self) -> None:
        """Disconnect from WebSocket subscriptions."""
        # Disconnect devices WebSocket
        if self._ws_devices_task:
            self._ws_devices_task.cancel()
            try:
                await self._ws_devices_task
            except asyncio.CancelledError:
                pass
            self._ws_devices_task = None

        if self._ws_devices:
            await self._ws_devices.close()
            self._ws_devices = None

        # Disconnect events WebSocket
        if self._ws_events_task:
            self._ws_events_task.cancel()
            try:
                await self._ws_events_task
            except asyncio.CancelledError:
                pass
            self._ws_events_task = None

        if self._ws_events:
            await self._ws_events.close()
            self._ws_events = None

        _LOGGER.info("WebSocket disconnected")

    async def _websocket_loop(self, endpoint: str, ws_type: str) -> None:
        """WebSocket connection loop with auto-reconnect.

        Args:
            endpoint: WebSocket endpoint path
            ws_type: Type of WebSocket ("devices" or "events")
        """
        session = await self._get_session()
        # Convert HTTP(S) base URL to WS(S) and construct full WebSocket URL
        ws_host = self.host.replace("https://", "wss://").replace("http://", "ws://")
        url = urljoin(ws_host, endpoint)

        while True:
            try:
                async with session.ws_connect(
                    url,
                    headers=self._headers,
                    ssl=self._verify_ssl,
                ) as ws:
                    if ws_type == "devices":
                        self._ws_devices = ws
                    else:
                        self._ws_events = ws

                    _LOGGER.info("%s WebSocket connected to %s", ws_type.title(), endpoint)

                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            data = msg.json()
                            if ws_type == "devices":
                                await self._handle_device_message(data)
                            else:
                                await self._handle_event_message(data)
                        elif msg.type == WSMsgType.ERROR:
                            _LOGGER.error("%s WebSocket error: %s", ws_type.title(), ws.exception())
                            break

            except asyncio.CancelledError:
                _LOGGER.debug("%s WebSocket loop cancelled", ws_type.title())
                raise
            except Exception as err:
                _LOGGER.error("%s WebSocket error: %s", ws_type.title(), err)

            # Reconnect after delay
            _LOGGER.info("Reconnecting %s WebSocket in 10 seconds...", ws_type)
            await asyncio.sleep(10)

    async def _handle_device_message(self, data: dict[str, Any]) -> None:
        """Handle incoming device WebSocket message.

        Args:
            data: Message data with format: {"type": "add", "item": {...}}
        """
        _LOGGER.debug("Device WebSocket message: %s", data)

        # Extract the action type and item
        action = data.get("type", "update")  # "add" maps to our "update" action
        item = data.get("item", {})

        if not item:
            return

        # Convert "add" type to action format that coordinator expects
        # The new API uses "add" for all updates, we map to "update" for our internal handling
        message = {
            "action": "update",
            "modelKey": item.get("modelKey"),
            "data": item,
        }

        # Notify all registered callbacks
        for callback in self._ws_device_callbacks:
            try:
                await callback(message)
            except Exception as err:
                _LOGGER.error("Error in device callback: %s", err)

    async def _handle_event_message(self, data: dict[str, Any]) -> None:
        """Handle incoming event WebSocket message.

        Args:
            data: Message data with format: {"type": "add", "item": {...}}
        """
        _LOGGER.debug("Event WebSocket message: %s", data)

        # Extract the action type and item
        action = data.get("type", "add")
        item = data.get("item", {})

        if not item:
            return

        # Notify all registered callbacks with the event data
        for callback in self._ws_event_callbacks:
            try:
                await callback(item)
            except Exception as err:
                _LOGGER.error("Error in event callback: %s", err)
