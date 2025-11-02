"""Config flow for UniFi Protect integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
import homeassistant.helpers.config_validation as cv

from .api import AuthenticationError, ConnectionError, UniFiProtectAPI
from .const import CONF_API_TOKEN, CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Args:
        hass: Home Assistant instance
        data: User input data

    Returns:
        Info dict with validation result

    Raises:
        AuthenticationError: If authentication fails
        ConnectionError: If connection fails
    """
    session = aiohttp_client.async_get_clientsession(hass)

    api = UniFiProtectAPI(
        host=data[CONF_HOST],
        api_token=data[CONF_API_TOKEN],
        session=session,
        verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )

    # Verify connection
    await api.verify_connection()

    # Get bootstrap to extract NVR name
    bootstrap = await api.get_bootstrap()
    nvr_name = bootstrap.get("nvr", {}).get("name", "UniFi Protect")

    await api.close()

    return {"title": nvr_name}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniFi Protect."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Validate the connection
                info = await validate_input(self.hass, user_input)

                # Check if already configured
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                # Create the config entry
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

            except AuthenticationError:
                _LOGGER.error("Authentication failed")
                errors["base"] = "invalid_auth"
            except ConnectionError:
                _LOGGER.error("Connection failed")
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Define the configuration schema
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=user_input.get(CONF_HOST) if user_input else "",
                ): cv.string,
                vol.Required(
                    CONF_API_TOKEN,
                    default=user_input.get(CONF_API_TOKEN) if user_input else "",
                ): cv.string,
                vol.Optional(
                    CONF_VERIFY_SSL,
                    default=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
                    if user_input
                    else DEFAULT_VERIFY_SSL,
                ): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
