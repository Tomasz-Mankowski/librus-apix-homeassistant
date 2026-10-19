"""Config flow for the Librus APIX integration."""

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    BooleanSelector,
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
    CONF_AVERAGE_MINUS,
    CONF_AVERAGE_ONLY_COUNTED,
    CONF_AVERAGE_PLUS,
    CONF_AVERAGE_WEIGHTS,
    CONF_MESSAGE_COUNT,
    CONF_SERVER_URL,
    CONF_TIMEFRAME,
    DEFAULT_AVERAGE_OPTIONS,
    DEFAULT_OPTIONS,
    DOMAIN,
    INTERVAL_OPTIONS,
    MAX_GRADE_MODIFIER,
    MAX_INTERVAL,
    MAX_MESSAGE_COUNT,
    MAX_TIMEFRAME,
    MIN_INTERVAL,
    MIN_MESSAGE_COUNT,
    SECTION_DEVELOPER,
)
from .exceptions import LibrusAuthError, LibrusConnectionError, LibrusUnavailableError

_LOGGER = logging.getLogger(__name__)

USERNAME_SELECTOR = TextSelector(TextSelectorConfig(autocomplete="username"))
PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): USERNAME_SELECTOR,
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
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


REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): USERNAME_SELECTOR,
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
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


def averages_schema(values: dict[str, Any]) -> vol.Schema:
    """Schema of the average rules (weights, counting, plus and minus values)."""
    modifier = NumberSelector(
        NumberSelectorConfig(
            min=0, max=MAX_GRADE_MODIFIER, step=0.05, mode=NumberSelectorMode.BOX
        )
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_AVERAGE_WEIGHTS, default=values[CONF_AVERAGE_WEIGHTS]
            ): BooleanSelector(),
            vol.Required(
                CONF_AVERAGE_ONLY_COUNTED, default=values[CONF_AVERAGE_ONLY_COUNTED]
            ): BooleanSelector(),
            vol.Required(
                CONF_AVERAGE_PLUS, default=values[CONF_AVERAGE_PLUS]
            ): modifier,
            vol.Required(
                CONF_AVERAGE_MINUS, default=values[CONF_AVERAGE_MINUS]
            ): modifier,
        }
    )


def average_options(user_input: dict[str, Any]) -> dict[str, Any]:
    """Stored average rules: two switches and two numbers."""
    return {
        CONF_AVERAGE_WEIGHTS: bool(user_input[CONF_AVERAGE_WEIGHTS]),
        CONF_AVERAGE_ONLY_COUNTED: bool(user_input[CONF_AVERAGE_ONLY_COUNTED]),
        CONF_AVERAGE_PLUS: float(user_input[CONF_AVERAGE_PLUS]),
        CONF_AVERAGE_MINUS: float(user_input[CONF_AVERAGE_MINUS]),
    }


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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start a new login when Librus rejects the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again; the login must be the same account."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_mismatch()
            data = {
                **entry.data,
                CONF_USERNAME: username,
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            if error := await self._async_check_login(data):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                REAUTH_SCHEMA, {CONF_USERNAME: entry.data[CONF_USERNAME]}
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LibrusApixOptionsFlow:
        """Return the options flow."""
        return LibrusApixOptionsFlow()

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


class LibrusApixOptionsFlow(OptionsFlowWithReload):
    """Change the settings, then the average rules; the entry reloads after saving."""

    def __init__(self) -> None:
        """Start with no new settings."""
        self._settings: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {
            **DEFAULT_OPTIONS,
            **DEFAULT_AVERAGE_OPTIONS,
            **self.config_entry.options,
        }

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the settings with the current values."""
        if user_input is not None:
            self._settings = settings_options(user_input)
            return await self.async_step_averages()
        return self.async_show_form(
            step_id="init", data_schema=settings_schema(self._current)
        )

    async def async_step_averages(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the rules of the calculated averages with the current values."""
        if user_input is not None:
            return self.async_create_entry(
                data={**self._settings, **average_options(user_input)}
            )
        return self.async_show_form(
            step_id="averages", data_schema=averages_schema(self._current)
        )
