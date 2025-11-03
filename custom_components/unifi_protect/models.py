"""Data models for UniFi Protect."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import DOMAIN


@dataclass
class ProtectCamera:
    """Represents a UniFi Protect camera."""

    id: str
    name: str
    model: str
    type: str
    mac: str
    host: str
    state: str
    is_connected: bool
    is_recording: bool
    is_motion_detected: bool
    privacy_mode: bool
    recording_mode: str
    channels: list[dict[str, Any]]
    last_motion: int | None
    last_ring: int | None
    firmware_version: str
    hardware_revision: str
    # V1 API additional fields
    is_mic_enabled: bool
    osd_settings: dict[str, Any]
    led_settings: dict[str, Any]
    lcd_message: dict[str, Any] | None
    mic_volume: int
    active_patrol_slot: int | None
    video_mode: str
    hdr_type: str
    feature_flags: dict[str, Any]
    smart_detect_settings: dict[str, Any]
    # Additional sensor fields
    is_dark: bool
    uptime: int | None  # Uptime in seconds
    voltage: float | None  # Voltage for doorbells
    wdr_value: int | None  # WDR level
    zoom_position: int | None  # Zoom position (0-100)
    # Stats
    stats: dict[str, Any]  # Network and storage stats
    raw_data: dict[str, Any]

    @classmethod
    def from_api_data(cls, data: dict[str, Any]) -> ProtectCamera:
        """Create camera from API data.

        Args:
            data: Raw camera data from API (supports both bootstrap and v1 API formats)

        Returns:
            ProtectCamera instance
        """
        # Determine connection status
        # Integration API v1 uses 'state' field: "CONNECTED", "CONNECTING", "DISCONNECTED"
        # Older API used 'isConnected' boolean
        state = data.get("state", "DISCONNECTED")
        if "isConnected" in data:
            is_connected = data["isConnected"]
        else:
            # Derive from state field - consider CONNECTED or CONNECTING as connected
            is_connected = state in ("CONNECTED", "CONNECTING")

        return cls(
            id=data["id"],
            name=data.get("name", "Unknown Camera"),
            model=data.get("model", "Unknown"),
            type=data.get("type", "camera"),
            mac=data.get("mac", ""),
            host=data.get("host", ""),
            state=state,
            is_connected=is_connected,
            is_recording=data.get("isRecording", False),
            is_motion_detected=data.get("isMotionDetected", False),
            privacy_mode=data.get("privacyModeEnabled", False),
            recording_mode=data.get("recordingSettings", {}).get("mode", "never"),
            channels=data.get("channels", []),
            last_motion=data.get("lastMotion"),
            last_ring=data.get("lastRing"),
            firmware_version=data.get("firmwareVersion", ""),
            hardware_revision=data.get("hardwareRevision", ""),
            # V1 API fields
            is_mic_enabled=data.get("isMicEnabled", True),
            osd_settings=data.get("osdSettings", {}),
            led_settings=data.get("ledSettings", {}),
            lcd_message=data.get("lcdMessage"),
            mic_volume=data.get("micVolume", 100),
            active_patrol_slot=data.get("activePatrolSlot"),
            video_mode=data.get("videoMode", "default"),
            hdr_type=data.get("hdrType", "auto"),
            feature_flags=data.get("featureFlags", {}),
            smart_detect_settings=data.get("smartDetectSettings", {}),
            # Additional sensor fields
            is_dark=data.get("isDark", False),
            uptime=data.get("uptime"),
            voltage=data.get("voltage"),
            wdr_value=data.get("wdrValue"),
            zoom_position=data.get("zoomPosition"),
            stats=data.get("stats", {}),
            raw_data=data,
        )

    def update(self, data: dict[str, Any]) -> None:
        """Update camera with new data.

        Args:
            data: New camera data from API
        """
        if "name" in data:
            self.name = data["name"]
        if "state" in data:
            self.state = data["state"]
            # If isConnected not explicitly provided, derive from state
            if "isConnected" not in data:
                self.is_connected = self.state in ("CONNECTED", "CONNECTING")
        if "isConnected" in data:
            self.is_connected = data["isConnected"]
        if "isRecording" in data:
            self.is_recording = data["isRecording"]
        if "isMotionDetected" in data:
            self.is_motion_detected = data["isMotionDetected"]
        if "privacyModeEnabled" in data:
            self.privacy_mode = data["privacyModeEnabled"]
        if "lastMotion" in data:
            self.last_motion = data["lastMotion"]
        if "lastRing" in data:
            self.last_ring = data["lastRing"]

        # Update recording mode
        if "recordingSettings" in data:
            self.recording_mode = data["recordingSettings"].get("mode", self.recording_mode)

        # V1 API fields
        if "isMicEnabled" in data:
            self.is_mic_enabled = data["isMicEnabled"]
        if "osdSettings" in data:
            self.osd_settings = data["osdSettings"]
        if "ledSettings" in data:
            self.led_settings = data["ledSettings"]
        if "lcdMessage" in data:
            self.lcd_message = data["lcdMessage"]
        if "micVolume" in data:
            self.mic_volume = data["micVolume"]
        if "activePatrolSlot" in data:
            self.active_patrol_slot = data["activePatrolSlot"]
        if "videoMode" in data:
            self.video_mode = data["videoMode"]
        if "hdrType" in data:
            self.hdr_type = data["hdrType"]
        if "featureFlags" in data:
            self.feature_flags = data["featureFlags"]
        if "smartDetectSettings" in data:
            self.smart_detect_settings = data["smartDetectSettings"]

        # Additional sensor fields
        if "isDark" in data:
            self.is_dark = data["isDark"]
        if "uptime" in data:
            self.uptime = data["uptime"]
        if "voltage" in data:
            self.voltage = data["voltage"]
        if "wdrValue" in data:
            self.wdr_value = data["wdrValue"]
        if "zoomPosition" in data:
            self.zoom_position = data["zoomPosition"]
        if "stats" in data:
            self.stats = data["stats"]

        # Update raw data
        self.raw_data.update(data)

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self.id

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for Home Assistant.

        Returns:
            Device info dict
        """
        return {
            "identifiers": {(DOMAIN, self.id)},
            "name": self.name,
            "manufacturer": "Ubiquiti",
            "model": self.model,
            "sw_version": self.firmware_version,
            "hw_version": self.hardware_revision,
        }

    @property
    def has_smart_detect(self) -> bool:
        """Return if camera supports smart detections."""
        smart_types = self.feature_flags.get("smartDetectTypes", [])
        return len(smart_types) > 0

    @property
    def detected_object_types(self) -> list[str]:
        """Return list of currently detected smart object types."""
        return self.smart_detect_settings.get("objectTypes", [])

    @property
    def detected_audio_types(self) -> list[str]:
        """Return list of currently detected smart audio types."""
        return self.smart_detect_settings.get("audioTypes", [])

    @property
    def is_person_detected(self) -> bool:
        """Return if person is detected."""
        return "person" in self.detected_object_types

    @property
    def is_vehicle_detected(self) -> bool:
        """Return if vehicle is detected."""
        return "vehicle" in self.detected_object_types

    @property
    def is_package_detected(self) -> bool:
        """Return if package is detected."""
        return "package" in self.detected_object_types

    @property
    def is_animal_detected(self) -> bool:
        """Return if animal is detected."""
        return "animal" in self.detected_object_types

    @property
    def is_license_plate_detected(self) -> bool:
        """Return if license plate is detected."""
        return "licensePlate" in self.detected_object_types

    @property
    def is_face_detected(self) -> bool:
        """Return if face is detected."""
        return "face" in self.detected_object_types

    @property
    def is_smart_detected(self) -> bool:
        """Return if any smart detection is triggered."""
        return len(self.detected_object_types) > 0 or len(self.detected_audio_types) > 0


@dataclass
class ProtectSensor:
    """Represents a UniFi Protect sensor."""

    id: str
    name: str
    model: str
    type: str
    mac: str
    state: str
    is_connected: bool
    battery_level: int | None
    firmware_version: str
    # V1 API additional fields
    mount_type: str
    battery_is_low: bool
    stats: dict[str, Any]  # light, humidity, temperature stats
    light_settings: dict[str, Any]
    humidity_settings: dict[str, Any]
    temperature_settings: dict[str, Any]
    is_opened: bool
    open_status_changed_at: int | None
    is_motion_detected: bool
    motion_detected_at: int | None
    motion_settings: dict[str, Any]
    alarm_triggered_at: int | None
    alarm_settings: dict[str, Any]
    leak_detected_at: int | None
    external_leak_detected_at: int | None
    leak_settings: dict[str, Any]
    tampering_detected_at: int | None
    raw_data: dict[str, Any]

    @classmethod
    def from_api_data(cls, data: dict[str, Any]) -> ProtectSensor:
        """Create sensor from API data.

        Args:
            data: Raw sensor data from API (supports both bootstrap and v1 API formats)

        Returns:
            ProtectSensor instance
        """
        battery_status = data.get("batteryStatus", {})

        # Determine connection status (same logic as camera)
        state = data.get("state", "DISCONNECTED")
        if "isConnected" in data:
            is_connected = data["isConnected"]
        else:
            is_connected = state in ("CONNECTED", "CONNECTING")

        return cls(
            id=data["id"],
            name=data.get("name", "Unknown Sensor"),
            model=data.get("model", "Unknown"),
            type=data.get("type", "sensor"),
            mac=data.get("mac", ""),
            state=state,
            is_connected=is_connected,
            battery_level=battery_status.get("percentage"),
            firmware_version=data.get("firmwareVersion", ""),
            # V1 API fields
            mount_type=data.get("mountType", "none"),
            battery_is_low=battery_status.get("isLow", False),
            stats=data.get("stats", {}),
            light_settings=data.get("lightSettings", {}),
            humidity_settings=data.get("humiditySettings", {}),
            temperature_settings=data.get("temperatureSettings", {}),
            is_opened=data.get("isOpened", False),
            open_status_changed_at=data.get("openStatusChangedAt"),
            is_motion_detected=data.get("isMotionDetected", False),
            motion_detected_at=data.get("motionDetectedAt"),
            motion_settings=data.get("motionSettings", {}),
            alarm_triggered_at=data.get("alarmTriggeredAt"),
            alarm_settings=data.get("alarmSettings", {}),
            leak_detected_at=data.get("leakDetectedAt"),
            external_leak_detected_at=data.get("externalLeakDetectedAt"),
            leak_settings=data.get("leakSettings", {}),
            tampering_detected_at=data.get("tamperingDetectedAt"),
            raw_data=data,
        )

    def update(self, data: dict[str, Any]) -> None:
        """Update sensor with new data.

        Args:
            data: New sensor data from API
        """
        if "name" in data:
            self.name = data["name"]
        if "state" in data:
            self.state = data["state"]
            # If isConnected not explicitly provided, derive from state
            if "isConnected" not in data:
                self.is_connected = self.state in ("CONNECTED", "CONNECTING")
        if "isConnected" in data:
            self.is_connected = data["isConnected"]
        if "batteryStatus" in data:
            battery_status = data["batteryStatus"]
            self.battery_level = battery_status.get("percentage")
            self.battery_is_low = battery_status.get("isLow", False)

        # V1 API fields
        if "mountType" in data:
            self.mount_type = data["mountType"]
        if "stats" in data:
            self.stats = data["stats"]
        if "lightSettings" in data:
            self.light_settings = data["lightSettings"]
        if "humiditySettings" in data:
            self.humidity_settings = data["humiditySettings"]
        if "temperatureSettings" in data:
            self.temperature_settings = data["temperatureSettings"]
        if "isOpened" in data:
            self.is_opened = data["isOpened"]
        if "openStatusChangedAt" in data:
            self.open_status_changed_at = data["openStatusChangedAt"]
        if "isMotionDetected" in data:
            self.is_motion_detected = data["isMotionDetected"]
        if "motionDetectedAt" in data:
            self.motion_detected_at = data["motionDetectedAt"]
        if "motionSettings" in data:
            self.motion_settings = data["motionSettings"]
        if "alarmTriggeredAt" in data:
            self.alarm_triggered_at = data["alarmTriggeredAt"]
        if "alarmSettings" in data:
            self.alarm_settings = data["alarmSettings"]
        if "leakDetectedAt" in data:
            self.leak_detected_at = data["leakDetectedAt"]
        if "externalLeakDetectedAt" in data:
            self.external_leak_detected_at = data["externalLeakDetectedAt"]
        if "leakSettings" in data:
            self.leak_settings = data["leakSettings"]
        if "tamperingDetectedAt" in data:
            self.tampering_detected_at = data["tamperingDetectedAt"]

        # Update raw data
        self.raw_data.update(data)

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self.id

    @property
    def light_value(self) -> float | None:
        """Return current light value in Lux."""
        return self.stats.get("light", {}).get("value")

    @property
    def light_status(self) -> str:
        """Return light status (neutral, low, safe, high, unknown)."""
        return self.stats.get("light", {}).get("status", "unknown")

    @property
    def humidity_value(self) -> float | None:
        """Return current humidity percentage."""
        return self.stats.get("humidity", {}).get("value")

    @property
    def humidity_status(self) -> str:
        """Return humidity status (neutral, low, safe, high, unknown)."""
        return self.stats.get("humidity", {}).get("status", "unknown")

    @property
    def temperature_value(self) -> float | None:
        """Return current temperature in Celsius."""
        return self.stats.get("temperature", {}).get("value")

    @property
    def temperature_status(self) -> str:
        """Return temperature status (neutral, low, safe, high, unknown)."""
        return self.stats.get("temperature", {}).get("status", "unknown")

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for Home Assistant.

        Returns:
            Device info dict
        """
        return {
            "identifiers": {(DOMAIN, self.id)},
            "name": self.name,
            "manufacturer": "Ubiquiti",
            "model": self.model,
            "sw_version": self.firmware_version,
        }


@dataclass
class ProtectNVR:
    """Represents the UniFi Protect NVR/Console."""

    id: str
    name: str
    version: str
    model: str
    mac: str
    host: str
    is_recording: bool
    storage_available: int
    storage_total: int
    storage_used: int
    # V1 API additional fields
    doorbell_settings: dict[str, Any]
    raw_data: dict[str, Any]

    @classmethod
    def from_api_data(cls, data: dict[str, Any]) -> ProtectNVR:
        """Create NVR from API bootstrap data.

        Args:
            data: Bootstrap data from API (supports both bootstrap and v1 API formats)

        Returns:
            ProtectNVR instance
        """
        # Handle both bootstrap format (nested nvr) and v1 API format (direct)
        nvr_data = data.get("nvr", data)

        return cls(
            id=nvr_data.get("id", ""),
            name=nvr_data.get("name", "UniFi Protect"),
            version=nvr_data.get("version", ""),
            model=nvr_data.get("model", ""),
            mac=nvr_data.get("mac", ""),
            host=nvr_data.get("host", ""),
            is_recording=nvr_data.get("isRecording", False),
            storage_available=nvr_data.get("storageStats", {}).get("available", 0),
            storage_total=nvr_data.get("storageStats", {}).get("total", 0),
            storage_used=nvr_data.get("storageStats", {}).get("used", 0),
            # V1 API fields
            doorbell_settings=nvr_data.get("doorbellSettings", {}),
            raw_data=nvr_data,
        )

    def update(self, data: dict[str, Any]) -> None:
        """Update NVR with new data.

        Args:
            data: New NVR data from API
        """
        if "name" in data:
            self.name = data["name"]
        if "version" in data:
            self.version = data["version"]
        if "host" in data:
            self.host = data["host"]
        if "isRecording" in data:
            self.is_recording = data["isRecording"]
        if "storageStats" in data:
            storage_stats = data["storageStats"]
            self.storage_available = storage_stats.get("available", self.storage_available)
            self.storage_total = storage_stats.get("total", self.storage_total)
            self.storage_used = storage_stats.get("used", self.storage_used)
        if "doorbellSettings" in data:
            self.doorbell_settings = data["doorbellSettings"]

        # Update raw data
        self.raw_data.update(data)

    @property
    def storage_used_percent(self) -> float:
        """Calculate storage used percentage.

        Returns:
            Percentage of storage used
        """
        if self.storage_total > 0:
            return (self.storage_used / self.storage_total) * 100
        return 0.0

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for Home Assistant.

        Returns:
            Device info dict
        """
        return {
            "identifiers": {(DOMAIN, self.id)},
            "name": self.name,
            "manufacturer": "Ubiquiti",
            "model": self.model,
            "sw_version": self.version,
        }


@dataclass
class ProtectViewer:
    """Represents a UniFi Protect Viewer (display device)."""

    id: str
    name: str | None
    model_key: str
    state: str
    liveview: str | None
    stream_limit: int
    raw_data: dict[str, Any]

    @classmethod
    def from_api_data(cls, data: dict[str, Any]) -> ProtectViewer:
        """Create viewer from API data.

        Args:
            data: Raw viewer data from API

        Returns:
            ProtectViewer instance
        """
        return cls(
            id=data["id"],
            name=data.get("name"),
            model_key=data.get("modelKey", "viewer"),
            state=data.get("state", "DISCONNECTED"),
            liveview=data.get("liveview"),
            stream_limit=data.get("streamLimit", 0),
            raw_data=data,
        )

    def update(self, data: dict[str, Any]) -> None:
        """Update viewer with new data.

        Args:
            data: New viewer data from API
        """
        if "name" in data:
            self.name = data["name"]
        if "state" in data:
            self.state = data["state"]
        if "liveview" in data:
            self.liveview = data["liveview"]
        if "streamLimit" in data:
            self.stream_limit = data["streamLimit"]

        # Update raw data
        self.raw_data.update(data)

    @property
    def is_connected(self) -> bool:
        """Return if viewer is connected."""
        return self.state == "CONNECTED"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self.id

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for Home Assistant.

        Returns:
            Device info dict
        """
        return {
            "identifiers": {(DOMAIN, self.id)},
            "name": self.name or f"Viewer {self.id[:8]}",
            "manufacturer": "Ubiquiti",
            "model": "UniFi Viewer",
        }


@dataclass
class ProtectLiveviewSlot:
    """Represents a slot in a liveview."""

    cameras: list[str]
    cycle_mode: str
    cycle_interval: int

    @classmethod
    def from_api_data(cls, data: dict[str, Any]) -> ProtectLiveviewSlot:
        """Create slot from API data.

        Args:
            data: Raw slot data from API

        Returns:
            ProtectLiveviewSlot instance
        """
        return cls(
            cameras=data.get("cameras", []),
            cycle_mode=data.get("cycleMode", "time"),
            cycle_interval=data.get("cycleInterval", 30),
        )


@dataclass
class ProtectLiveview:
    """Represents a UniFi Protect Liveview configuration."""

    id: str
    name: str
    model_key: str
    is_default: bool
    is_global: bool
    owner: str
    layout: int
    slots: list[ProtectLiveviewSlot]
    raw_data: dict[str, Any]

    @classmethod
    def from_api_data(cls, data: dict[str, Any]) -> ProtectLiveview:
        """Create liveview from API data.

        Args:
            data: Raw liveview data from API

        Returns:
            ProtectLiveview instance
        """
        slots = [
            ProtectLiveviewSlot.from_api_data(slot_data)
            for slot_data in data.get("slots", [])
        ]

        return cls(
            id=data["id"],
            name=data.get("name", ""),
            model_key=data.get("modelKey", "liveview"),
            is_default=data.get("isDefault", False),
            is_global=data.get("isGlobal", False),
            owner=data.get("owner", ""),
            layout=data.get("layout", 1),
            slots=slots,
            raw_data=data,
        )

    def update(self, data: dict[str, Any]) -> None:
        """Update liveview with new data.

        Args:
            data: New liveview data from API
        """
        if "name" in data:
            self.name = data["name"]
        if "isDefault" in data:
            self.is_default = data["isDefault"]
        if "isGlobal" in data:
            self.is_global = data["isGlobal"]
        if "layout" in data:
            self.layout = data["layout"]
        if "slots" in data:
            self.slots = [
                ProtectLiveviewSlot.from_api_data(slot_data)
                for slot_data in data["slots"]
            ]

        # Update raw data
        self.raw_data.update(data)

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self.id

    @property
    def camera_count(self) -> int:
        """Return total number of cameras in this liveview."""
        return sum(len(slot.cameras) for slot in self.slots)


@dataclass
class ProtectLight:
    """Represents a UniFi Protect Light (smart floodlight)."""

    id: str
    name: str | None
    model_key: str
    state: str
    is_dark: bool
    is_light_on: bool
    is_light_force_enabled: bool
    is_pir_motion_detected: bool
    last_motion: int | None
    camera: str | None
    light_mode: str
    light_enable_at: str
    led_level: int
    pir_duration: int
    pir_sensitivity: int
    is_indicator_enabled: bool
    raw_data: dict[str, Any]

    @classmethod
    def from_api_data(cls, data: dict[str, Any]) -> ProtectLight:
        """Create light from API data.

        Args:
            data: Raw light data from API

        Returns:
            ProtectLight instance
        """
        light_mode_settings = data.get("lightModeSettings", {})
        light_device_settings = data.get("lightDeviceSettings", {})

        return cls(
            id=data["id"],
            name=data.get("name"),
            model_key=data.get("modelKey", "light"),
            state=data.get("state", "DISCONNECTED"),
            is_dark=data.get("isDark", False),
            is_light_on=data.get("isLightOn", False),
            is_light_force_enabled=data.get("isLightForceEnabled", False),
            is_pir_motion_detected=data.get("isPirMotionDetected", False),
            last_motion=data.get("lastMotion"),
            camera=data.get("camera"),
            light_mode=light_mode_settings.get("mode", "motion"),
            light_enable_at=light_mode_settings.get("enableAt", "dark"),
            led_level=light_device_settings.get("ledLevel", 6),
            pir_duration=light_device_settings.get("pirDuration", 15000),
            pir_sensitivity=light_device_settings.get("pirSensitivity", 50),
            is_indicator_enabled=light_device_settings.get("isIndicatorEnabled", True),
            raw_data=data,
        )

    def update(self, data: dict[str, Any]) -> None:
        """Update light with new data.

        Args:
            data: New light data from API
        """
        if "name" in data:
            self.name = data["name"]
        if "state" in data:
            self.state = data["state"]
        if "isDark" in data:
            self.is_dark = data["isDark"]
        if "isLightOn" in data:
            self.is_light_on = data["isLightOn"]
        if "isLightForceEnabled" in data:
            self.is_light_force_enabled = data["isLightForceEnabled"]
        if "isPirMotionDetected" in data:
            self.is_pir_motion_detected = data["isPirMotionDetected"]
        if "lastMotion" in data:
            self.last_motion = data["lastMotion"]
        if "camera" in data:
            self.camera = data["camera"]

        # Update mode settings
        if "lightModeSettings" in data:
            settings = data["lightModeSettings"]
            if "mode" in settings:
                self.light_mode = settings["mode"]
            if "enableAt" in settings:
                self.light_enable_at = settings["enableAt"]

        # Update device settings
        if "lightDeviceSettings" in data:
            settings = data["lightDeviceSettings"]
            if "ledLevel" in settings:
                self.led_level = settings["ledLevel"]
            if "pirDuration" in settings:
                self.pir_duration = settings["pirDuration"]
            if "pirSensitivity" in settings:
                self.pir_sensitivity = settings["pirSensitivity"]
            if "isIndicatorEnabled" in settings:
                self.is_indicator_enabled = settings["isIndicatorEnabled"]

        # Update raw data
        self.raw_data.update(data)

    @property
    def is_connected(self) -> bool:
        """Return if light is connected."""
        return self.state == "CONNECTED"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self.id

    @property
    def brightness_percent(self) -> int:
        """Return brightness as percentage (0-100).

        LED level is 1-6, convert to percentage.
        """
        return int((self.led_level / 6) * 100)

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for Home Assistant.

        Returns:
            Device info dict
        """
        return {
            "identifiers": {(DOMAIN, self.id)},
            "name": self.name or f"Light {self.id[:8]}",
            "manufacturer": "Ubiquiti",
            "model": "UniFi Smart Flood Light",
        }


@dataclass
class ProtectChime:
    """Represents a UniFi Protect Chime (wireless doorbell chime)."""

    id: str
    name: str | None
    model_key: str
    state: str
    camera_ids: list[str]
    ring_settings: list[dict[str, Any]]
    last_ring: int | None  # Unix timestamp of last time chime rang
    raw_data: dict[str, Any]

    @classmethod
    def from_api_data(cls, data: dict[str, Any]) -> ProtectChime:
        """Create chime from API data.

        Args:
            data: Raw chime data from API

        Returns:
            ProtectChime instance
        """
        return cls(
            id=data["id"],
            name=data.get("name"),
            model_key=data.get("modelKey", "chime"),
            state=data.get("state", "DISCONNECTED"),
            camera_ids=data.get("cameraIds", []),
            ring_settings=data.get("ringSettings", []),
            last_ring=data.get("lastRing"),
            raw_data=data,
        )

    def update(self, data: dict[str, Any]) -> None:
        """Update chime with new data.

        Args:
            data: New chime data from API
        """
        if "name" in data:
            self.name = data["name"]
        if "state" in data:
            self.state = data["state"]
        if "cameraIds" in data:
            self.camera_ids = data["cameraIds"]
        if "ringSettings" in data:
            self.ring_settings = data["ringSettings"]
        if "lastRing" in data:
            self.last_ring = data["lastRing"]

        # Update raw data
        self.raw_data.update(data)

    @property
    def is_connected(self) -> bool:
        """Return if chime is connected."""
        return self.state == "CONNECTED"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self.id

    @property
    def paired_camera_count(self) -> int:
        """Return number of paired cameras."""
        return len(self.camera_ids)

    def get_ring_setting_for_camera(self, camera_id: str) -> dict[str, Any] | None:
        """Get ring settings for a specific camera.

        Args:
            camera_id: Camera UUID

        Returns:
            Ring settings dict or None if not found
        """
        for setting in self.ring_settings:
            if setting.get("cameraId") == camera_id:
                return setting
        return None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for Home Assistant.

        Returns:
            Device info dict
        """
        return {
            "identifiers": {(DOMAIN, self.id)},
            "name": self.name or f"Chime {self.id[:8]}",
            "manufacturer": "Ubiquiti",
            "model": "UniFi Chime",
        }
