"""Tests for setting up, unloading, reloading and removing an entry."""

from datetime import timedelta
import logging
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import requests
import requests_mock as rm

from custom_components.librus_apix.api import LibrusApi
from custom_components.librus_apix.const import CONF_INTERVAL_STUDENT, DOMAIN
from custom_components.librus_apix.exceptions import LibrusAuthError

from .common import MOCK_URL, SCHOOL

EXPECTED = {
    "student": ("Student", "Uczeń", "Zofia Testowa"),
    "class_name": ("Class", "Klasa", "5a"),
    "tutor": ("Tutor", "Wychowawca", "Magdalena Przykładowa"),
    "school": ("School", "Szkoła", SCHOOL),
    "student_number": ("Student number", "Numer w dzienniku", "14"),
    "lucky_number": ("Lucky number", "Szczęśliwy numerek", "7"),
}


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id
    return entity_id


@pytest.mark.usefixtures("mock_server")
async def test_setup_creates_one_device_with_its_entities(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """One student device: six information sensors with their values, messages."""
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, config_entry.entry_id), config_entry.entry_id
    )
    assert device is not None
    assert device.name == "Zofia Testowa"
    assert device.manufacturer == "Librus Synergia"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.configuration_url == MOCK_URL

    entities = er.async_entries_for_config_entry(
        er.async_get(hass), config_entry.entry_id
    )
    assert sorted(entity.unique_id.split("_", 1)[1] for entity in entities) == sorted(
        [*EXPECTED, "messages", "messages"]
    )
    assert {entity.device_id for entity in entities} == {device.id}
    for key, (name, _, value) in EXPECTED.items():
        state = hass.states.get(_entity_id(hass, config_entry, key))
        assert state.state == value
        assert state.attributes["friendly_name"] == f"Zofia Testowa {name}"


@pytest.mark.usefixtures("mock_server")
async def test_entity_names_in_polish(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """With Polish as the system language the entity names are Polish."""
    hass.config.language = "pl"

    await _setup(hass, config_entry)

    for key, (_, name, _) in EXPECTED.items():
        state = hass.states.get(_entity_id(hass, config_entry, key))
        assert state.attributes["friendly_name"] == f"Zofia Testowa {name}"


@pytest.mark.usefixtures("mock_server")
async def test_interval_comes_from_the_options(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The coordinator polls at the interval set in the options."""
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, CONF_INTERVAL_STUDENT: 120}
    )

    await _setup(hass, config_entry)

    coordinator = config_entry.runtime_data.student
    assert coordinator.update_interval == timedelta(minutes=120)


@pytest.mark.usefixtures("mock_server")
async def test_unload_and_reload(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Unload closes the session; reload brings back the same entities."""
    await _setup(hass, config_entry)
    entity_ids = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), config_entry.entry_id
        )
    }
    assert len(entity_ids) == 8

    with patch.object(LibrusApi, "close") as close:
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    close.assert_called_once()
    for entity_id in entity_ids:
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    entities = er.async_entries_for_config_entry(
        er.async_get(hass), config_entry.entry_id
    )
    assert {entity.entity_id for entity in entities} == entity_ids
    for entity_id in entity_ids:
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE


@pytest.mark.parametrize(
    "response",
    [{"status_code": 503, "text": "busy"}, {"exc": requests.ConnectionError}],
)
async def test_first_refresh_failure_retries(
    hass: HomeAssistant,
    requests_mock: rm.Mocker,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    response: dict,
) -> None:
    """Librus down at startup: the entry retries later, without a traceback."""
    requests_mock.get(f"{MOCK_URL}/informacja", **response)

    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    shown = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert shown
    assert not [r for r in shown if r.exc_info]


async def test_rejected_login_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A rejected login stops the setup and starts the reauth flow."""
    with patch.object(LibrusApi, "async_call", side_effect=LibrusAuthError("no")):
        await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


@pytest.mark.usefixtures("mock_server")
async def test_store_is_loaded_and_removed_with_the_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, hass_storage: dict
) -> None:
    """The stored document is loaded at setup and deleted with the entry."""
    key = f"{DOMAIN}.{config_entry.entry_id}"
    hass_storage[key] = {"version": 1, "key": key, "data": {"seen": {"a": [1]}}}

    await _setup(hass, config_entry)
    assert config_entry.runtime_data.store.data["seen"] == {"a": [1]}

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


@pytest.mark.usefixtures("mock_server")
async def test_failed_unload_keeps_the_session(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """If a platform cannot unload, the HTTP session stays open."""
    await _setup(hass, config_entry)

    with (
        patch.object(hass.config_entries, "async_unload_platforms", return_value=False),
        patch.object(LibrusApi, "close") as close,
    ):
        assert not await hass.config_entries.async_unload(config_entry.entry_id)

    close.assert_not_called()
