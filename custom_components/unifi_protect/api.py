"""UniFi Protect API Client for v6.1.79+."""
from __future__ import annotations

import asyncio
import logging
import ssl
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

        # Cache for RTSPS stream URLs (camera_id -> {"url": str, "expires": float})
        self._stream_cache: dict[str, dict[str, Any]] = {}

        # Cache for camera snapshots (camera_id -> {"data": bytes, "expires": float})
        # Snapshots cached for 2 seconds to avoid hammering the API
        self._snapshot_cache: dict[str, dict[str, Any]] = {}

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

    @property
    def _ssl_context(self) -> bool | ssl.SSLContext:
        """Get SSL context for requests.

        Returns:
            False if SSL verification disabled, True/SSLContext otherwise
        """
        if not self._verify_ssl:
            # Create SSL context that doesn't verify certificates
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context
        return True  # Use default SSL verification

    async def _get_session(self) -> ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            # Create connector with appropriate SSL context
            connector = aiohttp.TCPConnector(ssl=self._ssl_context if not self._verify_ssl else None)
            self._session = aiohttp.ClientSession(connector=connector)
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

        # Pass SSL context to request (important when using shared session from HA)
        # This overrides the session's default SSL configuration
        if "ssl" not in kwargs:
            kwargs["ssl"] = self._ssl_context

        _LOGGER.debug("Making %s request to %s", method, url)

        try:
            async with session.request(
                method,
                url,
                headers=self._headers,
                **kwargs,
            ) as response:
                _LOGGER.debug("Response status: %s for %s %s", response.status, method, endpoint)

                # Handle authentication errors
                if response.status == 401:
                    _LOGGER.error("Authentication failed: Invalid API token")
                    raise AuthenticationError("Invalid API token. Please check your API token in UniFi Protect settings.")

                if response.status == 403:
                    _LOGGER.error("Authentication failed: Insufficient permissions")
                    raise AuthenticationError("API token has insufficient permissions. Ensure the token has full access.")

                # Handle not found
                if response.status == 404:
                    error_msg = f"Endpoint not found: {endpoint}"
                    # Log as debug for /nvr endpoint since it's expected to not exist in some versions
                    if "/nvr" in endpoint:
                        _LOGGER.debug("%s (endpoint not available in this UniFi Protect version, will use fallback)", error_msg)
                    else:
                        _LOGGER.error("%s (This might indicate an API version mismatch)", error_msg)
                    raise ProtectAPIError(f"{error_msg}. This integration requires UniFi Protect v6.1.79 or later.")

                # Handle rate limiting
                if response.status == 429:
                    _LOGGER.warning("Rate limit exceeded (429) for %s", endpoint)
                    raise ConnectionError(
                        "UniFi Protect API rate limit exceeded. Too many requests sent too quickly. "
                        "Please wait a few seconds and try again."
                    )

                # Handle server errors
                if response.status == 500:
                    try:
                        error_data = await response.text()
                        _LOGGER.error("Server error (500) for %s: %s", url, error_data[:500])
                    except:
                        pass
                    raise ProtectAPIError(
                        f"UniFi Protect server error (500) at {endpoint}. "
                        f"This may indicate: 1) API endpoint not available in your UniFi Protect version, "
                        f"2) Server is still starting up, or 3) API token permissions issue. "
                        f"Required version: v6.1.79+. Check UniFi Protect logs for details."
                    )

                if response.status == 502:
                    _LOGGER.error("Bad Gateway (502): UniFi Protect service may be unavailable")
                    raise ConnectionError("UniFi Protect service is unavailable (502 Bad Gateway). The service may be restarting.")

                if response.status == 503:
                    _LOGGER.error("Service Unavailable (503)")
                    raise ConnectionError("UniFi Protect service is temporarily unavailable (503). Please try again in a few moments.")

                # Raise for any other error status
                response.raise_for_status()

                # Handle empty responses
                if response.status == 204:
                    return {}

                # Parse JSON response
                try:
                    return await response.json()
                except aiohttp.ContentTypeError as err:
                    _LOGGER.error("Invalid JSON response from %s: %s", url, err)
                    response_text = await response.text()
                    _LOGGER.debug("Response content: %s", response_text[:500])
                    raise ProtectAPIError(f"Invalid JSON response from {endpoint}")

        except AuthenticationError:
            # Re-raise authentication errors as-is
            raise
        except ConnectionError:
            # Re-raise connection errors as-is
            raise
        except ProtectAPIError:
            # Re-raise API errors as-is
            raise
        except aiohttp.ClientConnectorError as err:
            _LOGGER.error("Connection error: Cannot reach %s - %s", self.host, err)
            raise ConnectionError(
                f"Cannot connect to UniFi Protect at {self.host}. "
                f"Please check: 1) Host/IP address is correct, 2) UniFi Protect is running, "
                f"3) Network connectivity, 4) Firewall settings."
            ) from err
        except aiohttp.ClientSSLError as err:
            _LOGGER.error("SSL error connecting to %s: %s", self.host, err)
            raise ConnectionError(
                f"SSL certificate error connecting to {self.host}. "
                f"If using self-signed certificate, disable 'Verify SSL' in configuration."
            ) from err
        except aiohttp.ClientError as err:
            _LOGGER.error("HTTP client error: %s", err)
            raise ConnectionError(f"Connection error: {err}") from err
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout connecting to %s", self.host)
            raise ConnectionError(f"Connection timeout. UniFi Protect at {self.host} did not respond in time.") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error making request to %s", url)
            raise ProtectAPIError(f"Unexpected error: {err}") from err

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

    async def get_nvr_bootstrap(self) -> dict[str, Any]:
        """Get full NVR data from bootstrap endpoint (includes storage stats).

        This endpoint provides complete NVR information including storage statistics
        which are not available in the Integration API v1 endpoints.

        Returns:
            Full bootstrap data with NVR including storageStats

        Raises:
            AuthenticationError: If authentication fails
            ConnectionError: If connection fails
        """
        return await self.get("/proxy/protect/api/bootstrap")

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
                ssl=self._ssl_context,
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

    async def play_chime(self, chime_id: str, repeat_times: int = 1) -> None:
        """Play/ring the chime manually.

        Args:
            chime_id: Chime UUID
            repeat_times: How many times to repeat the chime (1-10, default 1)
        """
        if not 1 <= repeat_times <= 10:
            raise ValueError("repeat_times must be between 1 and 10")

        await self.post(
            f"/proxy/protect/integration/v1/chimes/{chime_id}/play",
            json={"repeatTimes": repeat_times},
        )

    async def reboot_chime(self, chime_id: str) -> None:
        """Reboot chime device.

        Args:
            chime_id: Chime UUID
        """
        await self.post(
            f"/proxy/protect/integration/v1/chimes/{chime_id}/reboot"
        )

    async def reboot_light(self, light_id: str) -> None:
        """Reboot light (floodlight) device.

        Args:
            light_id: Light UUID
        """
        await self.post(
            f"/proxy/protect/integration/v1/lights/{light_id}/reboot"
        )

    async def reboot_viewer(self, viewer_id: str) -> None:
        """Reboot viewer device.

        Args:
            viewer_id: Viewer UUID
        """
        await self.post(
            f"/proxy/protect/integration/v1/viewers/{viewer_id}/reboot"
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
            ProtectAPIError: If API version incompatible
        """
        _LOGGER.info("Verifying connection to UniFi Protect at %s", self.host)

        try:
            # Try to get application info to verify connection (v6+ API)
            app_info = await self.get_application_info()
            _LOGGER.info("Successfully connected to UniFi Protect. Version info: %s",
                        app_info.get("version", "unknown"))
            return True
        except AuthenticationError as err:
            _LOGGER.error("Authentication failed: %s", err)
            raise
        except ConnectionError as err:
            _LOGGER.error("Connection failed: %s", err)
            raise
        except ProtectAPIError as err:
            # Check if this is a version issue
            if "500" in str(err) or "404" in str(err):
                _LOGGER.error(
                    "API endpoint error. This may indicate UniFi Protect version is older than v6.1.79. "
                    "Error: %s", err
                )
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error verifying connection")
            raise ProtectAPIError(f"Failed to verify connection: {err}") from err

    async def get_bootstrap(self) -> dict[str, Any]:
        """Get bootstrap data containing all devices and settings using Integration API v1.

        This method fetches data from multiple v1 endpoints sequentially with delays
        to avoid rate limiting. Combined into a bootstrap-like structure for compatibility.

        Returns:
            Bootstrap data with all cameras, sensors, lights, chimes, and configuration (includes injected host field in nvr data)
        """
        _LOGGER.debug("Fetching bootstrap data from Integration API v1 endpoints")

        # Fetch data sequentially with small delays to avoid rate limiting
        # UniFi Protect API has rate limits, so we can't fetch all endpoints simultaneously

        nvr_data = {}
        cameras_data = []
        sensors_data = []
        lights_data = []
        chimes_data = []
        viewers_data = []
        liveviews_data = []

        try:
            # Fetch NVR data first - try v1 endpoint, fallback to application info
            try:
                nvr_data = await self.get_nvr_v1()
                await asyncio.sleep(0.2)  # 200ms delay
            except ProtectAPIError as err:
                # If NVR v1 endpoint doesn't exist, try application info as fallback
                if "not found" in str(err).lower():
                    _LOGGER.info("NVR v1 endpoint not available, using application info instead")
                    try:
                        nvr_data = await self.get_application_info()
                        await asyncio.sleep(0.2)
                    except Exception as app_err:
                        _LOGGER.warning("Error fetching application info: %s", app_err)
                else:
                    _LOGGER.warning("Error fetching nvr data: %s", err)
            except Exception as err:
                _LOGGER.warning("Error fetching nvr data: %s", err)

            # Fetch cameras
            try:
                cameras_data = await self.get_cameras_v1()
                await asyncio.sleep(0.2)
            except Exception as err:
                _LOGGER.warning("Error fetching cameras data: %s", err)

            # Fetch sensors
            try:
                sensors_data = await self.get_sensors_v1()
                await asyncio.sleep(0.2)
            except Exception as err:
                _LOGGER.warning("Error fetching sensors data: %s", err)

            # Fetch lights
            try:
                lights_data = await self.get_lights_v1()
                await asyncio.sleep(0.2)
            except Exception as err:
                _LOGGER.warning("Error fetching lights data: %s", err)

            # Fetch chimes
            try:
                chimes_data = await self.get_chimes()
                await asyncio.sleep(0.2)
            except Exception as err:
                _LOGGER.warning("Error fetching chimes data: %s", err)

            # Fetch viewers
            try:
                viewers_data = await self.get_viewers()
                await asyncio.sleep(0.2)
            except Exception as err:
                _LOGGER.warning("Error fetching viewers data: %s", err)

            # Fetch liveviews
            try:
                liveviews_data = await self.get_liveviews()
            except Exception as err:
                _LOGGER.warning("Error fetching liveviews data: %s", err)

            # Fetch storage stats from bootstrap endpoint
            # Integration API v1 doesn't include storage in NVR endpoint
            try:
                full_bootstrap = await self.get_nvr_bootstrap()
                if full_bootstrap and "nvr" in full_bootstrap:
                    nvr_with_storage = full_bootstrap["nvr"]
                    # Merge storage stats into our nvr_data
                    if "storageStats" in nvr_with_storage:
                        nvr_data["storageStats"] = nvr_with_storage["storageStats"]
                        _LOGGER.debug("Added storage stats to NVR data")
                await asyncio.sleep(0.2)
            except Exception as err:
                _LOGGER.warning("Error fetching storage stats: %s", err)

            # Combine into bootstrap structure
            bootstrap_data = {
                "nvr": nvr_data,
                "cameras": cameras_data,
                "sensors": sensors_data,
                "lights": lights_data,
                "chimes": chimes_data,
                "viewers": viewers_data,
                "liveviews": liveviews_data,
            }

            _LOGGER.debug("Successfully fetched bootstrap data: %d cameras, %d sensors, %d lights, %d chimes",
                         len(cameras_data), len(sensors_data), len(lights_data), len(chimes_data))

            return bootstrap_data

        except Exception as err:
            _LOGGER.error("Error fetching bootstrap data: %s", err)
            raise

    async def get_cameras(self) -> list[dict[str, Any]]:
        """Get all cameras using Integration API v1.

        Returns:
            List of camera data
        """
        return await self.get_cameras_v1()

    async def get_camera(self, camera_id: str) -> dict[str, Any]:
        """Get specific camera data using Integration API v1.

        Args:
            camera_id: Camera UUID

        Returns:
            Camera data
        """
        return await self.get_camera_v1(camera_id)

    async def set_recording_mode(
        self, camera_id: str, mode: str
    ) -> dict[str, Any]:
        """Set camera recording mode using Integration API v1.

        Args:
            camera_id: Camera UUID
            mode: Recording mode (always, never, motion, detections)

        Returns:
            Updated camera data
        """
        return await self.patch(
            f"/proxy/protect/integration/v1/cameras/{camera_id}",
            json={"recordingSettings": {"mode": mode}},
        )

    async def set_privacy_mode(
        self, camera_id: str, enabled: bool
    ) -> dict[str, Any]:
        """Enable/disable privacy mode on camera using Integration API v1.

        Args:
            camera_id: Camera UUID
            enabled: Privacy mode state

        Returns:
            Updated camera data
        """
        return await self.patch(
            f"/proxy/protect/integration/v1/cameras/{camera_id}",
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
        speaker_settings: dict[str, Any] | None = None,
        video_mode: str | None = None,
        hdr_type: str | None = None,
        smart_detect_settings: dict[str, Any] | None = None,
        wdr_value: int | None = None,
        zoom_position: int | None = None,
    ) -> dict[str, Any]:
        """Update camera settings using v1 API.

        Args:
            camera_id: Camera UUID
            name: Camera name
            osd_settings: On Screen Display settings (isNameEnabled, isDateEnabled, isLogoEnabled, isDebugEnabled, overlayLocation)
            led_settings: LED settings (isEnabled)
            lcd_message: LCD doorbell message (type, resetAt, text)
            mic_volume: Microphone volume (0-100)
            speaker_settings: Speaker settings (volume, isEnabled, areSpeakersMuted)
            video_mode: Video mode (default, highFps, sport, slowShutter, lprReflex, lprNoneReflex)
            hdr_type: HDR mode (auto, on, off)
            smart_detect_settings: Smart detection settings (objectTypes, audioTypes)
            wdr_value: WDR level (0-3)
            zoom_position: Zoom position (0-100)

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
        if speaker_settings is not None:
            # Validate volume if present
            if "volume" in speaker_settings:
                if not 0 <= speaker_settings["volume"] <= 100:
                    raise ValueError("Speaker volume must be between 0 and 100")
            data["speakerSettings"] = speaker_settings
        if video_mode is not None:
            data["videoMode"] = video_mode
        if hdr_type is not None:
            data["hdrType"] = hdr_type
        if smart_detect_settings is not None:
            data["smartDetectSettings"] = smart_detect_settings
        if wdr_value is not None:
            if not 0 <= wdr_value <= 3:
                raise ValueError("WDR value must be between 0 and 3")
            data["wdrValue"] = wdr_value
        if zoom_position is not None:
            if not 0 <= zoom_position <= 100:
                raise ValueError("Zoom position must be between 0 and 100")
            data["zoomPosition"] = zoom_position

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
            f"/proxy/protect/v1/cameras/{camera_id}/rtsps-stream",
            json={"qualities": qualities},
        )

    def get_cached_stream_url(self, camera_id: str) -> str | None:
        """Get cached stream URL for camera.

        Args:
            camera_id: Camera UUID

        Returns:
            Cached stream URL or None if not cached or expired
        """
        import time

        if camera_id not in self._stream_cache:
            return None

        cache_entry = self._stream_cache[camera_id]
        # Check if cache entry has expired (cache for 30 minutes)
        if time.time() > cache_entry["expires"]:
            del self._stream_cache[camera_id]
            return None

        return cache_entry["url"]

    def set_cached_stream_url(self, camera_id: str, url: str) -> None:
        """Cache stream URL for camera.

        Args:
            camera_id: Camera UUID
            url: Stream URL to cache
        """
        import time

        # Cache for 30 minutes (1800 seconds)
        self._stream_cache[camera_id] = {
            "url": url,
            "expires": time.time() + 1800,
        }

    async def get_camera_rtsps_streams(
        self, camera_id: str
    ) -> dict[str, str | None] | None:
        """Get existing RTSPS streams for camera.

        Args:
            camera_id: Camera UUID

        Returns:
            Dictionary with quality levels and their RTSPS URLs, or None if no streams exist
        """
        try:
            return await self.get(
                f"/proxy/protect/v1/cameras/{camera_id}/rtsps-stream"
            )
        except ProtectAPIError as err:
            # 404 means no streams created yet, which is normal
            if "404" in str(err) or "not found" in str(err).lower():
                _LOGGER.debug("No RTSPS streams exist yet for camera %s", camera_id)
                return None
            # Other errors should be raised
            raise

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
            f"/proxy/protect/v1/cameras/{camera_id}/rtsps-stream?{query_params}"
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
            url, headers=self._headers, params=params, ssl=self._ssl_context
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

    async def get_lights_v1(self) -> list[dict[str, Any]]:
        """Get all lights using v1 API.

        Returns:
            List of light data
        """
        return await self.get("/proxy/protect/integration/v1/lights")

    async def get_lights(self) -> list[dict[str, Any]]:
        """Get all lights using Integration API v1.

        Returns:
            List of light data
        """
        return await self.get_lights_v1()

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
        """Get URL for camera snapshot using Integration API v1.

        Args:
            camera_id: Camera UUID

        Returns:
            Snapshot URL
        """
        return urljoin(self.host, f"/proxy/protect/integration/v1/cameras/{camera_id}/snapshot")

    async def get_camera_snapshot(self, camera_id: str, force_refresh: bool = False) -> bytes | None:
        """Get camera snapshot image bytes with caching and retry logic.

        Args:
            camera_id: Camera UUID
            force_refresh: Force refresh cache (default: False)

        Returns:
            Image bytes or None if unavailable
        """
        import time

        # Check cache first (unless force refresh)
        if not force_refresh and camera_id in self._snapshot_cache:
            cache_entry = self._snapshot_cache[camera_id]
            # Cache for 2 seconds to avoid hammering the API
            if time.time() < cache_entry["expires"]:
                _LOGGER.debug("Using cached snapshot for camera %s", camera_id)
                return cache_entry["data"]

        url = self.get_camera_snapshot_url(camera_id)
        session = await self._get_session()

        # Retry logic: try up to 3 times with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 10 second timeout for snapshot fetch
                timeout = aiohttp.ClientTimeout(total=10)

                _LOGGER.debug("Fetching snapshot from %s (attempt %d/%d)", url, attempt + 1, max_retries)

                async with session.get(
                    url,
                    headers=self._headers,
                    ssl=self._ssl_context,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        image_data = await response.read()

                        # Validate we got actual image data
                        if not image_data or len(image_data) < 100:
                            _LOGGER.warning(
                                "Snapshot for %s returned suspiciously small data: %d bytes",
                                camera_id,
                                len(image_data) if image_data else 0
                            )
                            # Retry on next iteration
                            if attempt < max_retries - 1:
                                await asyncio.sleep(0.5 * (2 ** attempt))  # Exponential backoff
                                continue
                            return None

                        _LOGGER.debug("Successfully fetched snapshot: %d bytes", len(image_data))

                        # Cache the snapshot for 2 seconds
                        self._snapshot_cache[camera_id] = {
                            "data": image_data,
                            "expires": time.time() + 2.0,
                        }

                        return image_data

                    elif response.status == 404:
                        _LOGGER.warning("Camera %s not found (404)", camera_id)
                        return None

                    else:
                        _LOGGER.warning(
                            "Camera snapshot failed for %s: HTTP %s (attempt %d/%d)",
                            camera_id,
                            response.status,
                            attempt + 1,
                            max_retries
                        )

                        # Retry on server errors (5xx) or rate limiting (429)
                        if attempt < max_retries - 1 and response.status in (429, 500, 502, 503, 504):
                            await asyncio.sleep(0.5 * (2 ** attempt))  # Exponential backoff
                            continue

                        return None

            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Timeout fetching snapshot for %s (attempt %d/%d)",
                    camera_id,
                    attempt + 1,
                    max_retries
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                return None

            except Exception as err:
                _LOGGER.warning(
                    "Exception getting camera snapshot for %s (attempt %d/%d): %s",
                    camera_id,
                    attempt + 1,
                    max_retries,
                    err
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                return None

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
                    ssl=self._ssl_context,
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
            data: Message data with format: {"type": "add"|"update"|"remove", "item": {...}}

        The WebSocket sends updates for all device types:
        - camera, light, sensor, chime, viewer, speaker, bridge,
          doorlock, aiProcessor, aiPort, linkStation
        """
        message_type = data.get("type")
        item = data.get("item", {})

        if not item:
            _LOGGER.debug("WebSocket message has no item, skipping")
            return

        model_key = item.get("modelKey")
        device_id = item.get("id")
        device_name = item.get("name", "Unknown")

        _LOGGER.debug(
            "Device WebSocket: type=%s, modelKey=%s, id=%s, name=%s, state=%s",
            message_type,
            model_key,
            device_id,
            device_name,
            item.get("state"),
        )

        # Map API message type to internal action format
        # API uses "add" for all updates (both new devices and changes)
        # We map it to "update" for simplicity - coordinator handles both cases
        if message_type == "add":
            action = "update"  # Treat "add" as "update" - coordinator will handle appropriately
        elif message_type == "remove":
            action = "remove"
        else:
            # Default to update for any other type
            action = "update"

        # Build message in format coordinator expects
        message = {
            "action": action,
            "modelKey": model_key,
            "data": item,
        }

        # Notify all registered callbacks
        for callback in self._ws_device_callbacks:
            try:
                await callback(message)
            except Exception as err:
                _LOGGER.error("Error in device WebSocket callback: %s", err)

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
