"""Sensor platform for UniFi Protect."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera, ProtectChime, ProtectNVR, ProtectSensor

_LOGGER = logging.getLogger(__name__)


@dataclass
class ProtectSensorEntityDescription(SensorEntityDescription):
    """Describes UniFi Protect sensor entity."""

    key: str = ""


NVR_SENSORS: tuple[ProtectSensorEntityDescription, ...] = (
    ProtectSensorEntityDescription(
        key="storage_used",
        name="Storage Used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ProtectSensorEntityDescription(
        key="storage_available",
        name="Storage Available",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ProtectSensorEntityDescription(
        key="storage_used_percent",
        name="Storage Used Percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect sensors."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    # Add NVR sensors
    if coordinator.nvr:
        for description in NVR_SENSORS:
            entities.append(
                ProtectNVRSensorEntity(
                    coordinator,
                    description,
                )
            )

    # Add environmental sensors from UniFi Protect sensors
    for sensor_id, sensor in coordinator.sensors.items():
        # Add light sensor if enabled and has value
        if sensor.light_settings.get("isEnabled") and sensor.light_value is not None:
            entities.append(ProtectLightSensor(coordinator, sensor_id, sensor))

        # Add humidity sensor if enabled and has value
        if sensor.humidity_settings.get("isEnabled") and sensor.humidity_value is not None:
            entities.append(ProtectHumiditySensor(coordinator, sensor_id, sensor))

        # Add temperature sensor if enabled and has value
        if sensor.temperature_settings.get("isEnabled") and sensor.temperature_value is not None:
            entities.append(ProtectTemperatureSensor(coordinator, sensor_id, sensor))

        # Add battery level sensor
        if sensor.battery_level is not None:
            entities.append(ProtectBatterySensor(coordinator, sensor_id, sensor))

    # Add chime sensors
    for chime_id, chime in coordinator.chimes.items():
        # Add paired camera count sensor
        entities.append(ProtectChimePairedCamerasSensor(coordinator, chime_id, chime))
        # Add last ring sensor
        entities.append(ProtectChimeLastRingSensor(coordinator, chime_id, chime))

    async_add_entities(entities)


class ProtectNVRSensorEntity(
    CoordinatorEntity[ProtectDataUpdateCoordinator], SensorEntity
):
    """Representation of a UniFi Protect NVR sensor."""

    _attr_has_entity_name = True
    entity_description: ProtectSensorEntityDescription

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        description: ProtectSensorEntityDescription,
    ) -> None:
        """Initialize the sensor.

        Args:
            coordinator: The data update coordinator
            description: Entity description
        """
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.nvr.id}_{description.key}"
        self._attr_device_info = coordinator.nvr.device_info

    @property
    def nvr(self) -> ProtectNVR:
        """Return the NVR object."""
        return self.coordinator.nvr

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.nvr is not None

    @property
    def native_value(self) -> int | float | None:
        """Return the state of the sensor."""
        if not self.available:
            return None

        if self.entity_description.key == "storage_used":
            return self.nvr.storage_used
        elif self.entity_description.key == "storage_available":
            return self.nvr.storage_available
        elif self.entity_description.key == "storage_used_percent":
            return round(self.nvr.storage_used_percent, 1)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "is_recording": self.nvr.is_recording,
            "storage_total": self.nvr.storage_total,
        }

        # Add doorbell settings if available
        if self.nvr.doorbell_settings:
            attrs["doorbell_default_message"] = self.nvr.doorbell_settings.get("defaultMessageText")
            attrs["doorbell_message_timeout_ms"] = self.nvr.doorbell_settings.get("defaultMessageResetTimeoutMs")
            attrs["doorbell_custom_messages"] = self.nvr.doorbell_settings.get("customMessages", [])

        return attrs


class ProtectLightSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], SensorEntity):
    """Sensor for ambient light level from UniFi Protect sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LIGHT_LUX
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the light sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_light"
        self._attr_name = "Light"
        self._attr_device_info = sensor.device_info
        self._attr_icon = "mdi:brightness-5"

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
    def native_value(self) -> float | None:
        """Return the light level in Lux."""
        return self.sensor.light_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "status": self.sensor.light_status,
            "low_threshold": self.sensor.light_settings.get("lowThreshold"),
            "high_threshold": self.sensor.light_settings.get("highThreshold"),
        }


class ProtectHumiditySensor(CoordinatorEntity[ProtectDataUpdateCoordinator], SensorEntity):
    """Sensor for humidity from UniFi Protect sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the humidity sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_humidity"
        self._attr_name = "Humidity"
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
    def native_value(self) -> float | None:
        """Return the humidity percentage."""
        return self.sensor.humidity_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "status": self.sensor.humidity_status,
            "low_threshold": self.sensor.humidity_settings.get("lowThreshold"),
            "high_threshold": self.sensor.humidity_settings.get("highThreshold"),
        }


class ProtectTemperatureSensor(CoordinatorEntity[ProtectDataUpdateCoordinator], SensorEntity):
    """Sensor for temperature from UniFi Protect sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_temperature"
        self._attr_name = "Temperature"
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
    def native_value(self) -> float | None:
        """Return the temperature in Celsius."""
        return self.sensor.temperature_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "status": self.sensor.temperature_status,
            "low_threshold": self.sensor.temperature_settings.get("lowThreshold"),
            "high_threshold": self.sensor.temperature_settings.get("highThreshold"),
        }


class ProtectBatterySensor(CoordinatorEntity[ProtectDataUpdateCoordinator], SensorEntity):
    """Sensor for battery level from UniFi Protect sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        sensor_id: str,
        sensor: ProtectSensor,
    ) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator)
        self.sensor_id = sensor_id
        self._attr_unique_id = f"{sensor_id}_battery"
        self._attr_name = "Battery"
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
    def native_value(self) -> int | None:
        """Return the battery level percentage."""
        return self.sensor.battery_level

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "is_low": self.sensor.battery_is_low,
        }


class ProtectChimePairedCamerasSensor(
    CoordinatorEntity[ProtectDataUpdateCoordinator], SensorEntity
):
    """Sensor for number of cameras paired to a chime."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-ring"
    _attr_native_unit_of_measurement = "cameras"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        chime_id: str,
        chime: ProtectChime,
    ) -> None:
        """Initialize the paired cameras sensor."""
        super().__init__(coordinator)
        self.chime_id = chime_id
        self._attr_unique_id = f"{chime_id}_paired_cameras"
        self._attr_name = "Paired Cameras"
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
    def native_value(self) -> int:
        """Return the number of paired cameras."""
        return self.chime.paired_camera_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        camera_names = []
        for camera_id in self.chime.camera_ids:
            if camera_id in self.coordinator.cameras:
                camera_names.append(self.coordinator.cameras[camera_id].name or camera_id)
            else:
                camera_names.append(camera_id)

        return {
            "camera_ids": self.chime.camera_ids,
            "camera_names": camera_names,
            "is_connected": self.chime.is_connected,
            "state": self.chime.state,
        }


class ProtectChimeLastRingSensor(
    CoordinatorEntity[ProtectDataUpdateCoordinator], SensorEntity
):
    """Sensor for last time the chime rang."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-ring-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        chime_id: str,
        chime: ProtectChime,
    ) -> None:
        """Initialize the last ring sensor."""
        super().__init__(coordinator)
        self.chime_id = chime_id
        self._attr_unique_id = f"{chime_id}_last_ring"
        self._attr_name = "Last Ring"
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
    def native_value(self):
        """Return the last ring timestamp."""
        if self.chime.last_ring is None:
            return None

        # Convert Unix timestamp (seconds) to datetime
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self.chime.last_ring, tz=timezone.utc)
