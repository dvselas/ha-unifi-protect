"""The UniFi Protect integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client, entity_registry as er

from .api import UniFiProtectAPI
from .const import CONF_API_TOKEN, CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL, DOMAIN
from .coordinator import ProtectDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# List the platforms that your integration supports
PLATFORMS: list[Platform] = [
    Platform.CAMERA,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.NUMBER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Protect from a config entry."""
    _LOGGER.debug("Setting up UniFi Protect integration")

    # Get configuration
    host = entry.data[CONF_HOST]
    api_token = entry.data[CONF_API_TOKEN]
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

    # Create API client
    session = aiohttp_client.async_get_clientsession(hass)
    api = UniFiProtectAPI(
        host=host,
        api_token=api_token,
        session=session,
        verify_ssl=verify_ssl,
    )

    # Create coordinator
    coordinator = ProtectDataUpdateCoordinator(hass, api)

    # Setup coordinator (fetch initial data and connect WebSocket)
    await coordinator.async_setup()

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register services
    await async_setup_services(hass)

    # Forward the setup to the platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _get_device_id_from_entity_id(hass: HomeAssistant, entity_id: str) -> str:
    """Get device/camera ID from entity_id.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID like "camera.front_door"

    Returns:
        Device UUID

    Raises:
        HomeAssistantError: If entity not found or invalid
    """
    registry = er.async_get(hass)
    entity_entry = registry.async_get(entity_id)

    if not entity_entry:
        raise HomeAssistantError(f"Entity {entity_id} not found")

    # For cameras, the unique_id is the camera_id
    # For other entities, unique_id might be like "camera_id_sensor_type"
    # So we return the unique_id for cameras, or extract the device id from unique_id
    unique_id = entity_entry.unique_id

    # If unique_id contains underscores, it might be "device_id_entity_type"
    # For camera entities, unique_id is just the camera_id
    return unique_id


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for UniFi Protect."""

    async def handle_ptz_start_patrol(call):
        """Handle PTZ start patrol service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])
            slot = call.data["slot"]

            # Get coordinator from any entry
            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.ptz_start_patrol(camera_id, slot)
                    _LOGGER.info("Started PTZ patrol on camera %s, slot %s", camera_id, slot)
                    break
        except Exception as err:
            _LOGGER.error("Failed to start PTZ patrol: %s", err)
            raise HomeAssistantError(f"Failed to start PTZ patrol: {err}") from err

    async def handle_ptz_stop_patrol(call):
        """Handle PTZ stop patrol service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])

            # Get coordinator from any entry
            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.ptz_stop_patrol(camera_id)
                    _LOGGER.info("Stopped PTZ patrol on camera %s", camera_id)
                    break
        except Exception as err:
            _LOGGER.error("Failed to stop PTZ patrol: %s", err)
            raise HomeAssistantError(f"Failed to stop PTZ patrol: {err}") from err

    async def handle_ptz_goto_preset(call):
        """Handle PTZ goto preset service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])
            preset = call.data["preset"]

            # Get coordinator from any entry
            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.ptz_goto_preset(camera_id, preset)
                    _LOGGER.info("Moved camera %s to preset %s", camera_id, preset)
                    break
        except Exception as err:
            _LOGGER.error("Failed to goto PTZ preset: %s", err)
            raise HomeAssistantError(f"Failed to goto PTZ preset: {err}") from err

    async def handle_trigger_alarm(call):
        """Handle trigger alarm service call."""
        trigger_id = call.data["trigger_id"]

        # Get coordinator from any entry
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, ProtectDataUpdateCoordinator):
                try:
                    await coordinator.api.trigger_alarm(trigger_id)
                    _LOGGER.info("Alarm triggered with ID: %s", trigger_id)
                except Exception as err:
                    _LOGGER.error("Failed to trigger alarm %s: %s", trigger_id, err)
                break

    async def handle_set_camera_mic_volume(call):
        """Handle set camera mic volume service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])
            volume = call.data["volume"]

            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.update_camera(camera_id, mic_volume=volume)
                    await coordinator.async_request_refresh()
                    _LOGGER.info("Set mic volume for camera %s to %s", camera_id, volume)
                    break
        except Exception as err:
            _LOGGER.error("Failed to set mic volume: %s", err)
            raise HomeAssistantError(f"Failed to set mic volume: {err}") from err

    async def handle_set_camera_video_mode(call):
        """Handle set camera video mode service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])
            mode = call.data["mode"]

            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.update_camera(camera_id, video_mode=mode)
                    await coordinator.async_request_refresh()
                    _LOGGER.info("Set video mode for camera %s to %s", camera_id, mode)
                    break
        except Exception as err:
            _LOGGER.error("Failed to set video mode: %s", err)
            raise HomeAssistantError(f"Failed to set video mode: {err}") from err

    async def handle_set_camera_hdr_mode(call):
        """Handle set camera HDR mode service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])
            mode = call.data["mode"]

            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.update_camera(camera_id, hdr_type=mode)
                    await coordinator.async_request_refresh()
                    _LOGGER.info("Set HDR mode for camera %s to %s", camera_id, mode)
                    break
        except Exception as err:
            _LOGGER.error("Failed to set HDR mode: %s", err)
            raise HomeAssistantError(f"Failed to set HDR mode: {err}") from err

    async def handle_set_camera_osd_settings(call):
        """Handle set camera OSD settings service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])
            osd_settings = {}

            if "show_name" in call.data:
                osd_settings["isNameEnabled"] = call.data["show_name"]
            if "show_date" in call.data:
                osd_settings["isDateEnabled"] = call.data["show_date"]
            if "show_logo" in call.data:
                osd_settings["isLogoEnabled"] = call.data["show_logo"]
            if "show_debug" in call.data:
                osd_settings["isDebugEnabled"] = call.data["show_debug"]
            if "overlay_location" in call.data:
                osd_settings["overlayLocation"] = call.data["overlay_location"]

            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.update_camera(camera_id, osd_settings=osd_settings)
                    await coordinator.async_request_refresh()
                    _LOGGER.info("Updated OSD settings for camera %s", camera_id)
                    break
        except Exception as err:
            _LOGGER.error("Failed to set OSD settings: %s", err)
            raise HomeAssistantError(f"Failed to set OSD settings: {err}") from err

    async def handle_set_camera_lcd_message(call):
        """Handle set doorbell LCD message service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])
            message_type = call.data["message_type"]

            lcd_message = {"type": message_type}

            if "custom_text" in call.data and call.data["custom_text"]:
                lcd_message["text"] = call.data["custom_text"]

            if "reset_at" in call.data:
                reset_at = call.data["reset_at"]
                lcd_message["resetAt"] = None if reset_at == 0 else reset_at

            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.update_camera(camera_id, lcd_message=lcd_message)
                    await coordinator.async_request_refresh()
                    _LOGGER.info("Set LCD message for doorbell %s", camera_id)
                    break
        except Exception as err:
            _LOGGER.error("Failed to set LCD message: %s", err)
            raise HomeAssistantError(f"Failed to set LCD message: {err}") from err

    async def handle_set_smart_detect_settings(call):
        """Handle set smart detection settings service call."""
        try:
            camera_id = _get_device_id_from_entity_id(hass, call.data["entity_id"])
            smart_detect_settings = {}

            if "object_types" in call.data:
                smart_detect_settings["objectTypes"] = call.data["object_types"]
            if "audio_types" in call.data:
                smart_detect_settings["audioTypes"] = call.data["audio_types"]

            for entry_id, coordinator in hass.data[DOMAIN].items():
                if isinstance(coordinator, ProtectDataUpdateCoordinator):
                    await coordinator.api.update_camera(
                        camera_id, smart_detect_settings=smart_detect_settings
                    )
                    await coordinator.async_request_refresh()
                    _LOGGER.info("Updated smart detection settings for camera %s", camera_id)
                    break
        except Exception as err:
            _LOGGER.error("Failed to set smart detection settings: %s", err)
            raise HomeAssistantError(f"Failed to set smart detection settings: {err}") from err

    async def handle_upload_asset_file(call):
        """Handle upload asset file service call."""
        import os
        import mimetypes

        file_path = call.data["file_path"]
        file_type = call.data.get("file_type", "animations")

        # Validate file exists
        if not os.path.isfile(file_path):
            _LOGGER.error("File not found: %s", file_path)
            return

        # Determine content type
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            # Default to common types
            ext = os.path.splitext(file_path)[1].lower()
            content_type_map = {
                ".gif": "image/gif",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4",
                ".wav": "audio/wave",
                ".caf": "audio/x-caf",
            }
            content_type = content_type_map.get(ext, "application/octet-stream")

        filename = os.path.basename(file_path)

        # Read file data
        try:
            with open(file_path, "rb") as f:
                file_data = f.read()
        except Exception as err:
            _LOGGER.error("Failed to read file %s: %s", file_path, err)
            return

        # Upload to all coordinators
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, ProtectDataUpdateCoordinator):
                try:
                    result = await coordinator.api.upload_asset_file(
                        file_type, file_data, filename, content_type
                    )
                    _LOGGER.info(
                        "Uploaded asset file: %s (ID: %s)",
                        result.get("originalName"),
                        result.get("name"),
                    )
                except Exception as err:
                    _LOGGER.error("Failed to upload asset file: %s", err)
                break

    async def handle_list_asset_files(call):
        """Handle list asset files service call."""
        file_type = call.data.get("file_type", "animations")

        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, ProtectDataUpdateCoordinator):
                try:
                    files = await coordinator.api.get_asset_files(file_type)
                    _LOGGER.info(
                        "Asset files (%s): %s",
                        file_type,
                        [f"{f.get('originalName')} (ID: {f.get('name')})" for f in files],
                    )
                    # Create persistent notification with file list
                    file_list = "\n".join(
                        [
                            f"- {f.get('originalName', 'Unknown')} (ID: {f.get('name', 'N/A')})"
                            for f in files
                        ]
                    )
                    hass.components.persistent_notification.create(
                        f"## UniFi Protect Asset Files ({file_type})\n\n{file_list if file_list else 'No files found'}",
                        title="UniFi Protect Asset Files",
                        notification_id="unifi_protect_asset_files",
                    )
                except Exception as err:
                    _LOGGER.error("Failed to list asset files: %s", err)
                break

    async def handle_pair_chime_to_camera(call):
        """Handle pair chime to camera service call."""
        chime_id = call.data["chime_id"]
        camera_id = call.data["camera_id"]
        pair = call.data.get("pair", True)

        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, ProtectDataUpdateCoordinator):
                try:
                    if chime_id not in coordinator.chimes:
                        _LOGGER.error("Chime %s not found", chime_id)
                        return

                    chime = coordinator.chimes[chime_id]
                    current_camera_ids = list(chime.camera_ids)

                    if pair:
                        # Add camera to chime
                        if camera_id not in current_camera_ids:
                            current_camera_ids.append(camera_id)
                            await coordinator.api.update_chime(
                                chime_id, camera_ids=current_camera_ids
                            )
                            await coordinator.async_request_refresh()
                            _LOGGER.info("Paired camera %s to chime %s", camera_id, chime_id)
                    else:
                        # Remove camera from chime
                        if camera_id in current_camera_ids:
                            current_camera_ids.remove(camera_id)
                            await coordinator.api.update_chime(
                                chime_id, camera_ids=current_camera_ids
                            )
                            await coordinator.async_request_refresh()
                            _LOGGER.info("Unpaired camera %s from chime %s", camera_id, chime_id)
                except Exception as err:
                    _LOGGER.error("Failed to pair/unpair chime: %s", err)
                break

    async def handle_set_chime_ring_settings(call):
        """Handle set chime ring settings service call."""
        chime_id = call.data["chime_id"]
        camera_id = call.data["camera_id"]

        ring_setting = {"cameraId": camera_id}

        if "volume" in call.data:
            ring_setting["volume"] = call.data["volume"]
        if "repeat_times" in call.data:
            ring_setting["repeatTimes"] = call.data["repeat_times"]
        if "ringtone_id" in call.data:
            ring_setting["ringtoneId"] = call.data["ringtone_id"]

        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, ProtectDataUpdateCoordinator):
                try:
                    if chime_id not in coordinator.chimes:
                        _LOGGER.error("Chime %s not found", chime_id)
                        return

                    chime = coordinator.chimes[chime_id]

                    # Get existing ring settings and update for this camera
                    ring_settings = []
                    found = False

                    for existing_setting in chime.ring_settings:
                        if existing_setting.get("cameraId") == camera_id:
                            # Update this camera's settings
                            updated = existing_setting.copy()
                            updated.update(ring_setting)
                            ring_settings.append(updated)
                            found = True
                        else:
                            # Keep other cameras unchanged
                            ring_settings.append(existing_setting)

                    # If camera not in ring settings, add it
                    if not found:
                        # Ensure all required fields
                        if "volume" not in ring_setting:
                            ring_setting["volume"] = 100
                        if "repeatTimes" not in ring_setting:
                            ring_setting["repeatTimes"] = 1
                        if "ringtoneId" not in ring_setting:
                            ring_setting["ringtoneId"] = ""
                        ring_settings.append(ring_setting)

                    await coordinator.api.update_chime(
                        chime_id, ring_settings=ring_settings
                    )
                    await coordinator.async_request_refresh()
                    _LOGGER.info(
                        "Updated chime %s ring settings for camera %s", chime_id, camera_id
                    )
                except Exception as err:
                    _LOGGER.error("Failed to set chime ring settings: %s", err)
                break

    # Register services only once
    if not hass.services.has_service(DOMAIN, "ptz_start_patrol"):
        hass.services.async_register(
            DOMAIN,
            "ptz_start_patrol",
            handle_ptz_start_patrol,
        )

    if not hass.services.has_service(DOMAIN, "ptz_stop_patrol"):
        hass.services.async_register(
            DOMAIN,
            "ptz_stop_patrol",
            handle_ptz_stop_patrol,
        )

    if not hass.services.has_service(DOMAIN, "ptz_goto_preset"):
        hass.services.async_register(
            DOMAIN,
            "ptz_goto_preset",
            handle_ptz_goto_preset,
        )

    if not hass.services.has_service(DOMAIN, "trigger_alarm"):
        hass.services.async_register(
            DOMAIN,
            "trigger_alarm",
            handle_trigger_alarm,
        )

    if not hass.services.has_service(DOMAIN, "set_camera_mic_volume"):
        hass.services.async_register(
            DOMAIN,
            "set_camera_mic_volume",
            handle_set_camera_mic_volume,
        )

    if not hass.services.has_service(DOMAIN, "set_camera_video_mode"):
        hass.services.async_register(
            DOMAIN,
            "set_camera_video_mode",
            handle_set_camera_video_mode,
        )

    if not hass.services.has_service(DOMAIN, "set_camera_hdr_mode"):
        hass.services.async_register(
            DOMAIN,
            "set_camera_hdr_mode",
            handle_set_camera_hdr_mode,
        )

    if not hass.services.has_service(DOMAIN, "set_camera_osd_settings"):
        hass.services.async_register(
            DOMAIN,
            "set_camera_osd_settings",
            handle_set_camera_osd_settings,
        )

    if not hass.services.has_service(DOMAIN, "set_camera_lcd_message"):
        hass.services.async_register(
            DOMAIN,
            "set_camera_lcd_message",
            handle_set_camera_lcd_message,
        )

    if not hass.services.has_service(DOMAIN, "set_smart_detect_settings"):
        hass.services.async_register(
            DOMAIN,
            "set_smart_detect_settings",
            handle_set_smart_detect_settings,
        )

    if not hass.services.has_service(DOMAIN, "upload_asset_file"):
        hass.services.async_register(
            DOMAIN,
            "upload_asset_file",
            handle_upload_asset_file,
        )

    if not hass.services.has_service(DOMAIN, "list_asset_files"):
        hass.services.async_register(
            DOMAIN,
            "list_asset_files",
            handle_list_asset_files,
        )

    if not hass.services.has_service(DOMAIN, "pair_chime_to_camera"):
        hass.services.async_register(
            DOMAIN,
            "pair_chime_to_camera",
            handle_pair_chime_to_camera,
        )

    if not hass.services.has_service(DOMAIN, "set_chime_ring_settings"):
        hass.services.async_register(
            DOMAIN,
            "set_chime_ring_settings",
            handle_set_chime_ring_settings,
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading UniFi Protect integration")

    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Shutdown coordinator
        coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_shutdown()

        # Remove data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
