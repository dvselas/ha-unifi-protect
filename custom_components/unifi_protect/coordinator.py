"""DataUpdateCoordinator for UniFi Protect."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UniFiProtectAPI, ProtectAPIError
from .const import DOMAIN
from .models import ProtectCamera, ProtectChime, ProtectLight, ProtectLiveview, ProtectNVR, ProtectSensor, ProtectViewer

_LOGGER = logging.getLogger(__name__)


class ProtectDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching UniFi Protect data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UniFiProtectAPI,
        update_interval: int = 30,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            api: UniFi Protect API client
            update_interval: Update interval in seconds
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api
        self.nvr: ProtectNVR | None = None
        self.cameras: dict[str, ProtectCamera] = {}
        self.sensors: dict[str, ProtectSensor] = {}
        self.viewers: dict[str, ProtectViewer] = {}
        self.liveviews: dict[str, ProtectLiveview] = {}
        self.lights: dict[str, ProtectLight] = {}
        self.chimes: dict[str, ProtectChime] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API.

        Returns:
            Dictionary containing all device data

        Raises:
            UpdateFailed: If update fails
        """
        _LOGGER.debug("Coordinator update triggered")
        try:
            # Get bootstrap data (contains everything)
            bootstrap = await self.api.get_bootstrap()

            # Update NVR
            self.nvr = ProtectNVR.from_api_data(bootstrap)

            # Fetch NVR v1 API data for additional details (doorbell settings)
            # If NVR endpoint not available, use application info instead
            try:
                nvr_v1_data = await self.api.get_nvr_v1()
                if self.nvr and nvr_v1_data:
                    self.nvr.update(nvr_v1_data)
            except Exception as err:
                # Try fallback to application info if NVR endpoint doesn't exist
                if "not found" in str(err).lower() or "404" in str(err):
                    _LOGGER.debug("NVR v1 endpoint not available, trying application info")
                    try:
                        app_info = await self.api.get_application_info()
                        if self.nvr and app_info:
                            self.nvr.update(app_info)
                    except Exception as app_err:
                        _LOGGER.debug("Error fetching application info: %s", app_err)
                else:
                    _LOGGER.warning("Error fetching NVR v1 API data: %s", err)
                # Don't fail the entire update if NVR v1 API fails

            # Update cameras
            cameras_data = bootstrap.get("cameras", [])
            current_camera_ids = set()

            for camera_data in cameras_data:
                camera_id = camera_data["id"]
                current_camera_ids.add(camera_id)

                if camera_id in self.cameras:
                    # Update existing camera
                    self.cameras[camera_id].update(camera_data)
                else:
                    # Add new camera
                    self.cameras[camera_id] = ProtectCamera.from_api_data(camera_data)
                    _LOGGER.info(
                        "Discovered new camera: %s (isConnected=%s, state=%s)",
                        camera_data.get("name"),
                        camera_data.get("isConnected"),
                        camera_data.get("state"),
                    )

            # Remove cameras that no longer exist
            removed_cameras = set(self.cameras.keys()) - current_camera_ids
            for camera_id in removed_cameras:
                _LOGGER.info("Removing camera: %s", self.cameras[camera_id].name)
                del self.cameras[camera_id]

            # Update sensors
            sensors_data = bootstrap.get("sensors", [])
            current_sensor_ids = set()

            for sensor_data in sensors_data:
                sensor_id = sensor_data["id"]
                current_sensor_ids.add(sensor_id)

                if sensor_id in self.sensors:
                    # Update existing sensor
                    self.sensors[sensor_id].update(sensor_data)
                else:
                    # Add new sensor
                    self.sensors[sensor_id] = ProtectSensor.from_api_data(sensor_data)
                    _LOGGER.info("Discovered new sensor: %s", sensor_data.get("name"))

            # Remove sensors that no longer exist
            removed_sensors = set(self.sensors.keys()) - current_sensor_ids
            for sensor_id in removed_sensors:
                _LOGGER.info("Removing sensor: %s", self.sensors[sensor_id].name)
                del self.sensors[sensor_id]

            # Update viewers (using new v1 API)
            try:
                viewers_data = await self.api.get_viewers()
                current_viewer_ids = set()

                for viewer_data in viewers_data:
                    viewer_id = viewer_data["id"]
                    current_viewer_ids.add(viewer_id)

                    if viewer_id in self.viewers:
                        # Update existing viewer
                        self.viewers[viewer_id].update(viewer_data)
                    else:
                        # Add new viewer
                        self.viewers[viewer_id] = ProtectViewer.from_api_data(viewer_data)
                        _LOGGER.info("Discovered new viewer: %s", viewer_data.get("name"))

                # Remove viewers that no longer exist
                removed_viewers = set(self.viewers.keys()) - current_viewer_ids
                for viewer_id in removed_viewers:
                    _LOGGER.info("Removing viewer: %s", self.viewers[viewer_id].name)
                    del self.viewers[viewer_id]
            except Exception as err:
                _LOGGER.warning("Error fetching viewers: %s", err)
                # Don't fail the entire update if viewers fail

            # Update liveviews (using new v1 API)
            try:
                liveviews_data = await self.api.get_liveviews()
                current_liveview_ids = set()

                for liveview_data in liveviews_data:
                    liveview_id = liveview_data["id"]
                    current_liveview_ids.add(liveview_id)

                    if liveview_id in self.liveviews:
                        # Update existing liveview
                        self.liveviews[liveview_id].update(liveview_data)
                    else:
                        # Add new liveview
                        self.liveviews[liveview_id] = ProtectLiveview.from_api_data(liveview_data)
                        _LOGGER.info("Discovered new liveview: %s", liveview_data.get("name"))

                # Remove liveviews that no longer exist
                removed_liveviews = set(self.liveviews.keys()) - current_liveview_ids
                for liveview_id in removed_liveviews:
                    _LOGGER.info("Removing liveview: %s", self.liveviews[liveview_id].name)
                    del self.liveviews[liveview_id]
            except Exception as err:
                _LOGGER.warning("Error fetching liveviews: %s", err)
                # Don't fail the entire update if liveviews fail

            # Update lights (using new v1 API)
            try:
                lights_data = await self.api.get_lights_v1()
                current_light_ids = set()

                for light_data in lights_data:
                    light_id = light_data["id"]
                    current_light_ids.add(light_id)

                    if light_id in self.lights:
                        # Update existing light
                        self.lights[light_id].update(light_data)
                    else:
                        # Add new light
                        self.lights[light_id] = ProtectLight.from_api_data(light_data)
                        _LOGGER.info("Discovered new light: %s", light_data.get("name"))

                # Remove lights that no longer exist
                removed_lights = set(self.lights.keys()) - current_light_ids
                for light_id in removed_lights:
                    _LOGGER.info("Removing light: %s", self.lights[light_id].name)
                    del self.lights[light_id]
            except Exception as err:
                _LOGGER.warning("Error fetching lights: %s", err)
                # Don't fail the entire update if lights fail

            # Update chimes (using new v1 API)
            try:
                chimes_data = await self.api.get_chimes()
                current_chime_ids = set()

                for chime_data in chimes_data:
                    chime_id = chime_data["id"]
                    current_chime_ids.add(chime_id)

                    if chime_id in self.chimes:
                        # Update existing chime
                        self.chimes[chime_id].update(chime_data)
                    else:
                        # Add new chime
                        self.chimes[chime_id] = ProtectChime.from_api_data(chime_data)
                        _LOGGER.info("Discovered new chime: %s", chime_data.get("name"))

                # Remove chimes that no longer exist
                removed_chimes = set(self.chimes.keys()) - current_chime_ids
                for chime_id in removed_chimes:
                    _LOGGER.info("Removing chime: %s", self.chimes[chime_id].name)
                    del self.chimes[chime_id]
            except Exception as err:
                _LOGGER.warning("Error fetching chimes: %s", err)
                # Don't fail the entire update if chimes fail

            _LOGGER.debug(
                "Update completed: %d cameras, %d sensors, %d lights, %d viewers, %d liveviews, %d chimes",
                len(self.cameras),
                len(self.sensors),
                len(self.lights),
                len(self.viewers),
                len(self.liveviews),
                len(self.chimes),
            )

            return {
                "nvr": self.nvr,
                "cameras": self.cameras,
                "sensors": self.sensors,
                "viewers": self.viewers,
                "liveviews": self.liveviews,
                "lights": self.lights,
                "chimes": self.chimes,
            }

        except ProtectAPIError as err:
            _LOGGER.error("Update failed with API error: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during update: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def async_setup(self) -> None:
        """Set up the coordinator."""
        _LOGGER.info("Setting up UniFi Protect coordinator")

        # Initial data fetch
        _LOGGER.debug("Performing initial data refresh")
        await self.async_config_entry_first_refresh()
        _LOGGER.info("Initial data refresh completed successfully")

        # Connect WebSocket for real-time updates
        _LOGGER.debug("Connecting WebSocket for real-time updates")
        self.api.register_device_callback(self._handle_device_update)
        self.api.register_event_callback(self._handle_event_update)
        await self.api.connect_websocket()
        _LOGGER.info("WebSocket connected successfully")

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        # Disconnect WebSocket
        self.api.unregister_device_callback(self._handle_device_update)
        self.api.unregister_event_callback(self._handle_event_update)
        await self.api.disconnect_websocket()

        # Close API connection
        await self.api.close()

    async def _handle_device_update(self, data: dict[str, Any]) -> None:
        """Handle device update from WebSocket.

        Args:
            data: Device update data with format: {"action": "update", "modelKey": "...", "data": {...}}
        """
        action = data.get("action")
        model_key = data.get("modelKey")
        payload = data.get("data", {})

        _LOGGER.debug(
            "WebSocket update: action=%s, modelKey=%s, id=%s",
            action,
            model_key,
            payload.get("id"),
        )

        # Handle camera updates
        if model_key == "camera":
            camera_id = payload.get("id")
            if not camera_id:
                return

            if action == "add":
                # New camera discovered
                self.cameras[camera_id] = ProtectCamera.from_api_data(payload)
                _LOGGER.info("Camera added via WebSocket: %s", payload.get("name"))
            elif action == "update":
                # Camera updated
                if camera_id in self.cameras:
                    self.cameras[camera_id].update(payload)
                else:
                    # Camera not in our list yet, add it
                    self.cameras[camera_id] = ProtectCamera.from_api_data(payload)
            elif action == "remove":
                # Camera removed
                if camera_id in self.cameras:
                    _LOGGER.info("Camera removed via WebSocket: %s", self.cameras[camera_id].name)
                    del self.cameras[camera_id]

        # Handle sensor updates
        elif model_key == "sensor":
            sensor_id = payload.get("id")
            if not sensor_id:
                return

            if action == "add":
                # New sensor discovered
                self.sensors[sensor_id] = ProtectSensor.from_api_data(payload)
                _LOGGER.info("Sensor added via WebSocket: %s", payload.get("name"))
            elif action == "update":
                # Sensor updated
                if sensor_id in self.sensors:
                    self.sensors[sensor_id].update(payload)
                else:
                    # Sensor not in our list yet, add it
                    self.sensors[sensor_id] = ProtectSensor.from_api_data(payload)
            elif action == "remove":
                # Sensor removed
                if sensor_id in self.sensors:
                    _LOGGER.info("Sensor removed via WebSocket: %s", self.sensors[sensor_id].name)
                    del self.sensors[sensor_id]

        # Handle NVR updates
        elif model_key == "nvr":
            if self.nvr and action == "update":
                self.nvr.raw_data.update(payload)

        # Handle viewer updates
        elif model_key == "viewer":
            viewer_id = payload.get("id")
            if not viewer_id:
                return

            if action == "add":
                # New viewer discovered
                self.viewers[viewer_id] = ProtectViewer.from_api_data(payload)
                _LOGGER.info("Viewer added via WebSocket: %s", payload.get("name"))
            elif action == "update":
                # Viewer updated
                if viewer_id in self.viewers:
                    self.viewers[viewer_id].update(payload)
                else:
                    # Viewer not in our list yet, add it
                    self.viewers[viewer_id] = ProtectViewer.from_api_data(payload)
            elif action == "remove":
                # Viewer removed
                if viewer_id in self.viewers:
                    _LOGGER.info("Viewer removed via WebSocket: %s", self.viewers[viewer_id].name)
                    del self.viewers[viewer_id]

        # Handle liveview updates
        elif model_key == "liveview":
            liveview_id = payload.get("id")
            if not liveview_id:
                return

            if action == "add":
                # New liveview discovered
                self.liveviews[liveview_id] = ProtectLiveview.from_api_data(payload)
                _LOGGER.info("Liveview added via WebSocket: %s", payload.get("name"))
            elif action == "update":
                # Liveview updated
                if liveview_id in self.liveviews:
                    self.liveviews[liveview_id].update(payload)
                else:
                    # Liveview not in our list yet, add it
                    self.liveviews[liveview_id] = ProtectLiveview.from_api_data(payload)
            elif action == "remove":
                # Liveview removed
                if liveview_id in self.liveviews:
                    _LOGGER.info("Liveview removed via WebSocket: %s", self.liveviews[liveview_id].name)
                    del self.liveviews[liveview_id]

        # Handle light updates
        elif model_key == "light":
            light_id = payload.get("id")
            if not light_id:
                return

            if action == "add":
                # New light discovered
                self.lights[light_id] = ProtectLight.from_api_data(payload)
                _LOGGER.info("Light added via WebSocket: %s", payload.get("name"))
            elif action == "update":
                # Light updated
                if light_id in self.lights:
                    self.lights[light_id].update(payload)
                else:
                    # Light not in our list yet, add it
                    self.lights[light_id] = ProtectLight.from_api_data(payload)
            elif action == "remove":
                # Light removed
                if light_id in self.lights:
                    _LOGGER.info("Light removed via WebSocket: %s", self.lights[light_id].name)
                    del self.lights[light_id]

        # Handle chime updates
        elif model_key == "chime":
            chime_id = payload.get("id")
            if not chime_id:
                return

            if action == "add":
                # New chime discovered
                self.chimes[chime_id] = ProtectChime.from_api_data(payload)
                _LOGGER.info("Chime added via WebSocket: %s", payload.get("name"))
            elif action == "update":
                # Chime updated
                if chime_id in self.chimes:
                    self.chimes[chime_id].update(payload)
                else:
                    # Chime not in our list yet, add it
                    self.chimes[chime_id] = ProtectChime.from_api_data(payload)
            elif action == "remove":
                # Chime removed
                if chime_id in self.chimes:
                    _LOGGER.info("Chime removed via WebSocket: %s", self.chimes[chime_id].name)
                    del self.chimes[chime_id]

        # Notify all listeners of the update
        self.async_set_updated_data(
            {
                "nvr": self.nvr,
                "cameras": self.cameras,
                "sensors": self.sensors,
                "viewers": self.viewers,
                "liveviews": self.liveviews,
                "lights": self.lights,
                "chimes": self.chimes,
            }
        )

    async def _handle_event_update(self, event_data: dict[str, Any]) -> None:
        """Handle event update from WebSocket.

        Args:
            event_data: Event data from WebSocket
        """
        event_id = event_data.get("id")
        event_type = event_data.get("type")
        device_id = event_data.get("device")

        _LOGGER.debug(
            "Event received: type=%s, device=%s, event_id=%s",
            event_type,
            device_id,
            event_id,
        )

        # Handle different event types
        if event_type == "ring":
            # Doorbell ring event
            if device_id in self.cameras:
                camera = self.cameras[device_id]
                camera.last_ring = event_data.get("start")
                _LOGGER.info("Doorbell ring detected: %s", camera.name)

        elif event_type in ["motion", "smartDetectZone", "smartDetectLine"]:
            # Motion or smart detection event
            if device_id in self.cameras:
                camera = self.cameras[device_id]
                camera.is_motion_detected = event_data.get("end") is None
                camera.last_motion = event_data.get("start")
                _LOGGER.debug("Motion event for camera: %s", camera.name)

        elif event_type == "lightMotion":
            # Light motion event
            if device_id in self.lights:
                light = self.lights[device_id]
                light.is_pir_motion_detected = event_data.get("end") is None
                light.last_motion = event_data.get("start")
                _LOGGER.debug("Light motion event: %s", light.name)

        # Notify listeners
        self.async_set_updated_data(
            {
                "nvr": self.nvr,
                "cameras": self.cameras,
                "sensors": self.sensors,
                "viewers": self.viewers,
                "liveviews": self.liveviews,
                "lights": self.lights,
                "chimes": self.chimes,
            }
        )
