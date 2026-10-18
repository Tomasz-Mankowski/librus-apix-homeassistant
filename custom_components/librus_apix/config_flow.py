"""Config flow for the Librus APIX integration."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

# Newer Home Assistant releases alias voluptuous to probatio; 2026.3 ships voluptuous.
import voluptuous as vol

from .const import DOMAIN

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


class LibrusApixConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Librus APIX."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the login form."""
        if user_input is not None:
            # The login check and entry creation are not implemented yet.
            return self.async_abort(reason="not_implemented")
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)
