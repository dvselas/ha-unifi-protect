"""Light platform for UniFi Protect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtectDataUpdateCoordinator
from .models import ProtectLight

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi Protect lights."""
    coordinator: ProtectDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Add all lights
    async_add_entities(
        ProtectLightEntity(coordinator, light_id, light)
        for light_id, light in coordinator.lights.items()
    )


class ProtectLightEntity(CoordinatorEntity[ProtectDataUpdateCoordinator], LightEntity):
    """Representation of a UniFi Protect light."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        coordinator: ProtectDataUpdateCoordinator,
        light_id: str,
        light: ProtectLight,
    ) -> None:
        """Initialize the light.

        Args:
            coordinator: The data update coordinator
            light_id: Light ID
            light: Light data
        """
        super().__init__(coordinator)
        self.light_id = light_id
        self._attr_unique_id = light_id
        self._attr_name = light.name
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
        """Return true if light is on."""
        return self.light.is_light_on or self.light.is_light_force_enabled

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light (0-255).

        UniFi lights have brightness 1-6, convert to 0-255.
        """
        # Convert 1-6 to 0-255
        return int((self.light.led_level / 6) * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        try:
            # Handle brightness if provided
            if ATTR_BRIGHTNESS in kwargs:
                # Convert 0-255 to 1-6
                brightness_255 = kwargs[ATTR_BRIGHTNESS]
                brightness_6 = max(1, int((brightness_255 / 255) * 6))
                await self.coordinator.api.set_light_brightness(
                    self.light_id, brightness_6
                )
            else:
                # Just turn on (force enable)
                await self.coordinator.api.update_light(
                    self.light_id, is_light_force_enabled=True
                )

            # Request coordinator update
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error turning on light %s: %s", self.entity_id, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        try:
            await self.coordinator.api.update_light(
                self.light_id, is_light_force_enabled=False
            )

            # Request coordinator update
            await self.coordinator.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Error turning off light %s: %s", self.entity_id, err)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes.

        Returns:
            Dictionary of extra attributes
        """
        return {
            "light_id": self.light_id,
            "light_mode": self.light.light_mode,
            "enable_at": self.light.light_enable_at,
            "is_dark": self.light.is_dark,
            "pir_motion_detected": self.light.is_pir_motion_detected,
            "last_motion": self.light.last_motion,
            "pir_sensitivity": self.light.pir_sensitivity,
            "pir_duration_ms": self.light.pir_duration,
            "paired_camera": self.light.camera,
        }
