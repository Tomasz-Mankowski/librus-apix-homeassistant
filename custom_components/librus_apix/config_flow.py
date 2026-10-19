"""Config flow for the Librus APIX integration."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

# Newer Home Assistant releases alias voluptuous to probatio; 2026.3 ships voluptuous.
import voluptuous as vol

from librus_apix.student_information import get_student_information

from .api import LibrusApi
from .const import (
    CONF_MESSAGE_COUNT,
    CONF_SERVER_URL,
    CONF_TIMEFRAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    INTERVAL_OPTIONS,
    MAX_INTERVAL,
    MAX_MESSAGE_COUNT,
    MAX_TIMEFRAME,
    MIN_INTERVAL,
    MIN_MESSAGE_COUNT,
    SECTION_DEVELOPER,
)
from .exceptions import LibrusAuthError, LibrusConnectionError, LibrusUnavailableError

_LOGGER = logging.getLogger(__name__)

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
        vol.Required(SECTION_DEVELOPER): section(
            vol.Schema(
                {
                    vol.Optional(CONF_SERVER_URL): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    )
                }
            ),
            {"collapsed": True},
        ),
    }
)


def _number(minimum: int, maximum: int, unit: str | None = None) -> NumberSelector:
    config = NumberSelectorConfig(
        min=minimum, max=maximum, step=1, mode=NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def settings_schema(values: dict[str, Any]) -> vol.Schema:
    """Schema of the settings (intervals, timeframe, message count)."""
    schema: dict[Any, Any] = {
        vol.Required(key, default=values[key]): _number(
            MIN_INTERVAL, MAX_INTERVAL, "min"
        )
        for key in INTERVAL_OPTIONS
    }
    schema[vol.Required(CONF_TIMEFRAME, default=values[CONF_TIMEFRAME])] = _number(
        0, MAX_TIMEFRAME
    )
    schema[vol.Required(CONF_MESSAGE_COUNT, default=values[CONF_MESSAGE_COUNT])] = (
        _number(MIN_MESSAGE_COUNT, MAX_MESSAGE_COUNT)
    )
    return vol.Schema(schema)


def settings_options(user_input: dict[str, Any]) -> dict[str, int]:
    """Stored options: every setting as a whole number."""
    return {key: int(user_input[key]) for key in DEFAULT_OPTIONS}


class LibrusApixConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Librus APIX: login, then settings."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with no account."""
        self._data: dict[str, Any] = {}
        self._title = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the login and password and check them."""
        errors: dict[str, str] = {}
        suggested: dict[str, Any] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            developer = user_input.get(SECTION_DEVELOPER, {})
            server_url = developer.get(CONF_SERVER_URL, "").strip().rstrip("/")
            suggested = {CONF_USERNAME: username, SECTION_DEVELOPER: developer}
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()
            data = {CONF_USERNAME: username, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            if server_url:
                data[CONF_SERVER_URL] = server_url
            if server_url and not server_url.startswith(("http://", "https://")):
                errors["base"] = "invalid_url"
            elif error := await self._async_check_login(data):
                errors["base"] = error
            else:
                self._data = data
                return await self.async_step_settings()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the poll intervals, schedule timeframe and message count."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._title, data=self._data, options=settings_options(user_input)
            )
        return self.async_show_form(
            step_id="settings", data_schema=settings_schema(DEFAULT_OPTIONS)
        )

    async def _async_check_login(self, data: dict[str, Any]) -> str | None:
        """Log in and read the student name. Return an error key or None."""
        api = LibrusApi(
            self.hass,
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
            base_url=data.get(CONF_SERVER_URL),
        )
        try:
            info = await api.async_call(get_student_information)
        except LibrusAuthError:
            return "invalid_auth"
        except LibrusUnavailableError as err:
            return "maintenance" if err.maintenance else "cannot_connect"
        except LibrusConnectionError:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error during the Librus login check")
            return "unknown"
        self._title = info.name
        return None
