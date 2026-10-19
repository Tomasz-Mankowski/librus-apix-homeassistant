"""Tests for the event entity base (F1, F16)."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.event import ATTR_EVENT_TYPE, EventEntityDescription
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    async_capture_events,
)

from custom_components.librus_apix.const import CONF_INTERVAL_STUDENT, DOMAIN
from custom_components.librus_apix.coordinator import LibrusCoordinator
from custom_components.librus_apix.event import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_STUDENT,
    LibrusEventEntity,
)


@dataclass
class Result:
    """A coordinator result with the ids of new items."""

    new: list[str] = field(default_factory=list)


class TestCoordinator(LibrusCoordinator[Result]):
    """Coordinator that returns the next prepared result."""

    __test__ = False

    def __init__(self, hass: HomeAssistant, entry: MockConfigEntry) -> None:
        super().__init__(hass, entry, MagicMock(), "test", CONF_INTERVAL_STUDENT)
        self.results: list[Result] = []

    async def _async_fetch(self) -> Result:
        return self.results.pop(0)


class TestEvent(LibrusEventEntity[TestCoordinator]):
    """Fires new_item for each new id."""

    __test__ = False

    def _events(self, data: Result) -> Iterable[tuple[str, dict[str, Any]]]:
        return [("new_item", {"id": item_id}) for item_id in data.new]


DESCRIPTION = EventEntityDescription(
    key="test", translation_key="test", event_types=["new_item"]
)


async def _entity(
    hass: HomeAssistant, entry: MockConfigEntry, *first: str
) -> tuple[TestCoordinator, TestEvent, list]:
    coordinator = TestCoordinator(hass, entry)
    coordinator.results.append(Result(list(first)))
    await coordinator.async_refresh()
    entity = TestEvent(coordinator, DESCRIPTION)
    entity.entity_id = "event.test"
    events = async_capture_events(hass, EVENT_STATE_CHANGED)
    platform = MockEntityPlatform(hass, domain="event", platform_name=DOMAIN)
    await platform.async_add_entities([entity])
    await hass.async_block_till_done()
    return coordinator, entity, events


def _fired(events: list) -> list[dict[str, Any]]:
    return [
        e.data["new_state"].attributes
        for e in events
        if e.data["entity_id"] == "event.test"
        and e.data["new_state"].attributes.get(ATTR_EVENT_TYPE)
    ]


async def test_items_of_the_first_poll_fire_when_added(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Items found by the first poll (new since the last run) fire on start."""
    _, _, events = await _entity(hass, config_entry, "a")

    fired = _fired(events)
    assert [(f[ATTR_EVENT_TYPE], f["id"]) for f in fired] == [("new_item", "a")]
    assert fired[0][ATTR_STUDENT] == "Zofia Testowa"
    assert fired[0][ATTR_CONFIG_ENTRY_ID] == config_entry.entry_id


async def test_three_new_items_fire_three_events_in_order(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """One state write per item, so a queued automation runs for each (F16)."""
    coordinator, _, events = await _entity(hass, config_entry)

    coordinator.results.append(Result(["x", "y", "z"]))
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert [f["id"] for f in _fired(events)] == ["x", "y", "z"]


async def test_a_result_fires_only_once(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Listeners called again for the same result fire nothing."""
    coordinator, _, events = await _entity(hass, config_entry, "a")

    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    assert [f["id"] for f in _fired(events)] == ["a"]


async def test_base_class_needs_events(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Subclasses must say which events a result fires."""
    coordinator = TestCoordinator(hass, config_entry)

    with pytest.raises(NotImplementedError):
        list(LibrusEventEntity(coordinator, DESCRIPTION)._events(Result()))
