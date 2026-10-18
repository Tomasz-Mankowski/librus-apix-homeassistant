"""Tests for the Librus APIX config flow."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.librus_apix.const import DOMAIN


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """The user step shows the login form without errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] is None
    assert set(result["data_schema"].schema) == {CONF_USERNAME, CONF_PASSWORD}


async def test_user_step_submit_aborts(hass: HomeAssistant) -> None:
    """Submitting the form aborts until the login check exists."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "student", CONF_PASSWORD: "secret"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_implemented"
