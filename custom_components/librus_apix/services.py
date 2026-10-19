"""Actions of the integration: read the content of a message (F7).

Reading a body in Librus marks the message read, so the content is read only on
request and only once; later calls return the copy from the store.
"""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er

# Newer Home Assistant releases alias voluptuous to probatio; 2026.3 ships voluptuous.
import voluptuous as vol

from .const import DOMAIN
from .coordinator import LibrusConfigEntry
from .exceptions import LibrusError

SERVICE_GET_MESSAGE_CONTENT = "get_message_content"
ATTR_MESSAGE_ID = "message_id"

GET_MESSAGE_CONTENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_MESSAGE_ID): cv.string,
    }
)


def _entry_of(hass: HomeAssistant, entity_id: str) -> LibrusConfigEntry:
    """Return the loaded entry (student) that owns the entity."""
    entity = er.async_get(hass).async_get(entity_id)
    entry = (
        hass.config_entries.async_get_entry(entity.config_entry_id)
        if entity and entity.platform == DOMAIN and entity.config_entry_id
        else None
    )
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_entity",
            translation_placeholders={"entity_id": entity_id},
        )
    return entry


async def _async_get_message_content(call: ServiceCall) -> ServiceResponse:
    """Return author, title, date, content and attachment names of a message."""
    entry = _entry_of(call.hass, call.data[ATTR_ENTITY_ID])
    msg_id = call.data[ATTR_MESSAGE_ID].strip()
    try:
        return await entry.runtime_data.messages.async_get_content(msg_id)
    except KeyError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_message",
            translation_placeholders={"message_id": msg_id},
        ) from err
    except LibrusError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="cannot_read_message",
            translation_placeholders={"error": str(err)},
        ) from err


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions (once, for all entries)."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_MESSAGE_CONTENT,
        _async_get_message_content,
        schema=GET_MESSAGE_CONTENT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
