"""Event platform for UniFi Protect."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectCamera

_LOGGER = logging.getLogger(__name__)


@dataclass
class ProtectEventEntityDescription(EventEntityDescription):
    """Describes UniFi Protect event entity."""

    key: str = ""


CAMERA_EVENT_ENTITIES: tuple[ProtectEventEntityDescription, ...] = (
    ProtectEventEntityDescription(
        key="doorbell",
        name="Doorbell",
        device_class=EventDeviceClass.DOORBELL,
        event_types=["ring"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect event entities."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[EventEntity] = []

    # Add doorbell event entities for doorbell cameras
    for camera_id, camera in coordinator.cameras.items():
        if camera.type == "doorbell":
            for description in CAMERA_EVENT_ENTITIES:
                entities.append(
                    ProtectDoorbellEventEntity(
                        coordinator,
                        camera_id,
                        camera,
                        description,
                    )
                )

    if entities:
        async_add_entities(entities)


class ProtectDoorbellEventEntity(
    CoordinatorEntity[ProtectDataUpdateCoordinator], EventEntity
):
    """Representation of a UniFi Protect doorbell event entity."""

    _attr_has_entity_name = True
    entity_description: ProtectEventEntityDescription

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        camera_id: str,
        camera: ProtectCamera,
        description: ProtectEventEntityDescription,
    ) -> None:
        """Initialize the event entity.

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
        self._last_event_id: str | None = None
        self._last_ring_time: int | None = None

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
        )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        # Register callback to handle ring events from coordinator
        self.coordinator.register_doorbell_callback(self.camera_id, self._handle_ring_event)

    async def async_will_remove_from_hass(self) -> None:
        """When entity is removed from hass."""
        await super().async_will_remove_from_hass()

        # Unregister callback
        self.coordinator.unregister_doorbell_callback(self.camera_id, self._handle_ring_event)

    def _handle_ring_event(self, event_data: dict[str, Any]) -> None:
        """Handle doorbell ring event from coordinator.

        Args:
            event_data: Event data with event_id and timestamp
        """
        event_id = event_data.get("event_id")
        ring_time = event_data.get("timestamp")

        # Only trigger if this is a new event (different timestamp)
        if ring_time and ring_time != self._last_ring_time:
            self._last_ring_time = ring_time
            self._last_event_id = event_id

            # Trigger the event with event_type and event attributes
            self._trigger_event(
                "ring",
                {
                    "event_id": event_id,
                    "camera_id": self.camera_id,
                    "camera_name": self.camera.name,
                    "timestamp": datetime.fromtimestamp(ring_time / 1000, tz=timezone.utc).isoformat(),
                },
            )
            self.async_write_ha_state()

            _LOGGER.debug(
                "Doorbell event triggered for %s: event_id=%s",
                self.camera.name,
                event_id,
            )
