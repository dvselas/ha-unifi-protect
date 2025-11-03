"""Binary sensor platform for UniFi Protect."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera, ProtectChime, ProtectLight, ProtectSensor

_LOGGER = logging.getLogger(__name__)


@dataclass
class ProtectBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes UniFi Protect binary sensor entity."""

    key: str = ""


CAMERA_BINARY_SENSORS: tuple[ProtectBinarySensorEntityDescription, ...] = (
    ProtectBinarySensorEntityDescription(
        key="motion",
        name="Motion",
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    ProtectBinarySensorEntityDescription(
        key="doorbell",
        name="Doorbell",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
    ),
    ProtectBinarySensorEntityDescription(
        key="online",
        name="Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    ProtectBinarySensorEntityDescription(
        key="dark",
        name="Is Dark",
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:brightness-4",
    ),
)

# Smart detection sensors (only for cameras with smart detect capability)
SMART_DETECT_SENSORS: tuple[ProtectBinarySensorEntityDescription, ...] = (
    ProtectBinarySensorEntityDescription(
        key="smart_obj",
        name="Smart Detection",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:shield-check",
    ),
    ProtectBinarySensorEntityDescription(
        key="person",
        name="Person Detected",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:human",
    ),
    ProtectBinarySensorEntityDescription(
        key="vehicle",
        name="Vehicle Detected",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:car",
    ),
    ProtectBinarySensorEntityDescription(
        key="package",
        name="Package Detected",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:package",
    ),
    ProtectBinarySensorEntityDescription(
        key="animal",
        name="Animal Detected",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:paw",
    ),
    ProtectBinarySensorEntityDescription(
        key="license_plate",
        name="License Plate Detected",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:card-account-details",
    ),
    ProtectBinarySensorEntityDescription(
        key="face",
        name="Face Detected",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:face-recognition",
    ),
)

LIGHT_BINARY_SENSORS: tuple[ProtectBinarySensorEntityDescription, ...] = (
    ProtectBinarySensorEntityDescription(
        key="dark",
        name="Is Dark",
        device_class=BinarySensorDeviceClass.LIGHT,
        icon="mdi:brightness-4",
    ),
    ProtectBinarySensorEntityDescription(
        key="motion",
        name="Motion Detected",
        device_class=BinarySensorDeviceClass.MOTION,
        icon="mdi:motion-sensor",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect binary sensors."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []

    # Add binary sensors for each camera
    for camera_id, camera in coordinator.cameras.items():
        for description in CAMERA_BINARY_SENSORS:
            # Skip doorbell sensor for non-doorbell cameras
            if description.key == "doorbell" and camera.type != "doorbell":
                continue

            entities.append(
                ProtectBinarySensorEntity(
                    coordinator,
                    camera_id,
                    camera,
                    description,
                )
            )

        # Add smart detection sensors if camera supports them
        if camera.has_smart_detect:
            for description in SMART_DETECT_SENSORS:
                entities.append(
                    ProtectBinarySensorEntity(
                        coordinator,
                        camera_id,
                        camera,
                        description,
                    )
                )

    # Add binary sensors for each sensor
    for sensor_id, sensor in coordinator.sensors.items():
        # Door/Window/Garage opened sensor
        if sensor.mount_type in ["door", "window", "garage"]:
            entities.append(ProtectOpenedSensor(coordinator, sensor_id, sensor))

        # Motion detection sensor
        if sensor.motion_settings.get("isEnabled"):
            entities.append(ProtectMotionSensor(coordinator, sensor_id, sensor))

        # Leak detection sensors
        if sensor.leak_settings.get("isInternalEnabled"):
            entities.append(ProtectLeakSensor(coordinator, sensor_id, sensor))
        if sensor.leak_settings.get("isExternalEnabled"):
            entities.append(ProtectExternalLeakSensor(coordinator, sensor_id, sensor))

        # Alarm sensor (smoke/CO)
        if sensor.alarm_settings.get("isEnabled"):
            entities.append(ProtectAlarmSensor(coordinator, sensor_id, sensor))

        # Tampering detection
        entities.append(ProtectTamperingSensor(coordinator, sensor_id, sensor))

        # Low battery sensor
        entities.append(ProtectLowBatterySensor(coordinator, sensor_id, sensor))

    # Add binary sensors for each chime
    for chime_id, chime in coordinator.chimes.items():
        # Connection status sensor
        entities.append(ProtectChimeConnectionSensor(coordinator, chime_id, chime))

    # Add binary sensors for each light (floodlight)
    for light_id, light in coordinator.lights.items():
        for description in LIGHT_BINARY_SENSORS:
            entities.append(
                ProtectLightBinarySensorEntity(
                    coordinator,
                    light_id,
                    light,
                    description,
                )
            )

    async_add_entities(entities)


class ProtectBinarySensorEntity(
    CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a UniFi Protect binary sensor."""

    _attr_has_entity_name = True
    entity_description: ProtectBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
        description: ProtectBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor.

        Args:
            coordinator: The data update coordinator
            camera_id: Camera ID
            camera: Camera data
            description: Entity description
        """
        super().__init__(coordinator)
        self.entity_description = description
        self.camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_{description.key}"
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
        )

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self.entity_description.key == "motion":
            return self.camera.is_motion_detected_recently
        elif self.entity_description.key == "doorbell":
            # Doorbell is "on" if it was recently pressed (within last 30 seconds)
            if self.camera.last_ring:
                from time import time
                return (time() * 1000 - self.camera.last_ring) < 30000
            return False
        elif self.entity_description.key == "online":
            return self.camera.is_connected
        elif self.entity_description.key == "dark":
            return self.camera.is_dark
        # Smart detection sensors
        elif self.entity_description.key == "smart_obj":
            return self.camera.is_smart_detected
        elif self.entity_description.key == "person":
            return self.camera.is_person_detected
        elif self.entity_description.key == "vehicle":
            return self.camera.is_vehicle_detected
        elif self.entity_description.key == "package":
            return self.camera.is_package_detected
        elif self.entity_description.key == "animal":
            return self.camera.is_animal_detected
        elif self.entity_description.key == "license_plate":
            return self.camera.is_license_plate_detected
        elif self.entity_description.key == "face":
            return self.camera.is_face_detected

        return False


class ProtectOpenedSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for door/window/garage opened status."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the opened sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_opened"
        self._attr_device_info = sensor.device_info

        # Set device class and name based on mount type
        if sensor.mount_type == "door":
            self._attr_device_class = BinarySensorDeviceClass.DOOR
            self._attr_name = "Door"
        elif sensor.mount_type == "window":
            self._attr_device_class = BinarySensorDeviceClass.WINDOW
            self._attr_name = "Window"
        elif sensor.mount_type == "garage":
            self._attr_device_class = BinarySensorDeviceClass.GARAGE_DOOR
            self._attr_name = "Garage Door"
        else:
            self._attr_device_class = BinarySensorDeviceClass.OPENING
            self._attr_name = "Opened"

    @property
    def sensor(self) -> ProtectSensor:
        """Return the sensor object."""
        return self.coordinator.sensors[self.sensor_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.sensor_id in self.coordinator.sensors
            and self.sensor.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if opened."""
        return self.sensor.is_opened


class ProtectMotionSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for motion detection."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOTION
    _attr_name = "Motion"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the motion sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_motion"
        self._attr_device_info = sensor.device_info

    @property
    def sensor(self) -> ProtectSensor:
        """Return the sensor object."""
        return self.coordinator.sensors[self.sensor_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.sensor_id in self.coordinator.sensors
            and self.sensor.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if motion detected."""
        return self.sensor.is_motion_detected


class ProtectLeakSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for internal leak detection."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_name = "Leak"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the leak sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_leak"
        self._attr_device_info = sensor.device_info

    @property
    def sensor(self) -> ProtectSensor:
        """Return the sensor object."""
        return self.coordinator.sensors[self.sensor_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.sensor_id in self.coordinator.sensors
            and self.sensor.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if leak detected."""
        return self.sensor.leak_detected_at is not None


class ProtectExternalLeakSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for external leak detection."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_name = "External Leak"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the external leak sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_external_leak"
        self._attr_device_info = sensor.device_info

    @property
    def sensor(self) -> ProtectSensor:
        """Return the sensor object."""
        return self.coordinator.sensors[self.sensor_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.sensor_id in self.coordinator.sensors
            and self.sensor.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if external leak detected."""
        return self.sensor.external_leak_detected_at is not None


class ProtectAlarmSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for smoke/CO alarm."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_name = "Alarm"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the alarm sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_alarm"
        self._attr_device_info = sensor.device_info

    @property
    def sensor(self) -> ProtectSensor:
        """Return the sensor object."""
        return self.coordinator.sensors[self.sensor_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.sensor_id in self.coordinator.sensors
            and self.sensor.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if alarm triggered."""
        return self.sensor.alarm_triggered_at is not None


class ProtectTamperingSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for tampering detection."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.TAMPER
    _attr_name = "Tampering"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the tampering sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_tampering"
        self._attr_device_info = sensor.device_info

    @property
    def sensor(self) -> ProtectSensor:
        """Return the sensor object."""
        return self.coordinator.sensors[self.sensor_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.sensor_id in self.coordinator.sensors
            and self.sensor.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if tampering detected."""
        return self.sensor.tampering_detected_at is not None


class ProtectLowBatterySensor(CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for low battery."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_name = "Low Battery"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the low battery sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_low_battery"
        self._attr_device_info = sensor.device_info

    @property
    def sensor(self) -> ProtectSensor:
        """Return the sensor object."""
        return self.coordinator.sensors[self.sensor_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.sensor_id in self.coordinator.sensors
            and self.sensor.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if battery is low."""
        return self.sensor.battery_is_low


class ProtectChimeConnectionSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for chime connection status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Connection"

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        chime_id: str,
        chime: ProtectChime,
    ) -> None:
        """Initialize the chime connection sensor."""
        super().__init__(coordinator)
        self.chime_id = chime_id
        self._attr_unique_id = f"{chime_id}_connection"
        self._attr_device_info = chime.device_info

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
        )

    @property
    def is_on(self) -> bool:
        """Return true if chime is connected."""
        return self.chime.is_connected


class ProtectLightBinarySensorEntity(
    CoordinatorEntity[ProtectDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a UniFi Protect light binary sensor."""

    _attr_has_entity_name = True
    entity_description: ProtectBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        light_id: str,
        light: ProtectLight,
        description: ProtectBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor.

        Args:
            coordinator: The data update coordinator
            light_id: Light ID
            light: Light data
            description: Entity description
        """
        super().__init__(coordinator)
        self.entity_description = description
        self.light_id = light_id
        self._attr_unique_id = f"{light_id}_{description.key}"
        self._attr_device_info = light.device_info

    @property
    def light(self) -> ProtectLight:
        """Return the light object."""
        return self.coordinator.lights[self.light_id]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.light_id in self.coordinator.lights
            and self.light.is_connected
        )

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self.entity_description.key == "dark":
            return self.light.is_dark
        elif self.entity_description.key == "motion":
            return self.light.is_pir_motion_detected_recently

        return False
