"""Tests for new-item tracking (F16, F17)."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.librus_apix import tracker as tracker_module
from custom_components.librus_apix.store import SAVE_DELAY, LibrusStore
from custom_components.librus_apix.tracker import Change, TrackedItem, Tracker


def items(*ids: str, value: str = "v", scope: str | None = None) -> list[TrackedItem]:
    """Tracked items with a snapshot {"value": value}."""
    return [TrackedItem(i, {"value": value}, f"item {i}", scope) for i in ids]


def kinds(changes: list[Change]) -> list[tuple[str, str]]:
    return [(change.kind, change.item_id) for change in changes]


@pytest.fixture
async def store(hass: HomeAssistant) -> LibrusStore:
    """An empty store of entry1."""
    store = LibrusStore(hass, "entry1")
    await store.async_load()
    return store


async def test_first_poll_fires_nothing(store: LibrusStore) -> None:
    """Items that exist on the first poll are only recorded."""
    tracker = Tracker(store, "messages")

    assert tracker.update(items("1", "2", "3")) == []
    assert list(store.data["tracker"]["messages"]["items"]) == ["1", "2", "3"]


async def test_three_new_items_fire_three_changes_in_order(store: LibrusStore) -> None:
    """Each new item is reported once, in the order of the poll."""
    tracker = Tracker(store, "messages")
    tracker.update(items("1"))

    changes = tracker.update(items("4", "3", "2", "1"))

    assert kinds(changes) == [("new", "4"), ("new", "3"), ("new", "2")]
    assert changes[0].item == "item 4"
    assert tracker.update(items("4", "3", "2", "1")) == []


async def test_restart_with_the_saved_store_fires_nothing(
    hass: HomeAssistant, store: LibrusStore, freezer: FrozenDateTimeFactory
) -> None:
    """The seen items survive a restart."""
    Tracker(store, "grades").update(items("1", "2"))
    freezer.tick(timedelta(seconds=SAVE_DELAY + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    restarted = LibrusStore(hass, "entry1")
    await restarted.async_load()

    assert Tracker(restarted, "grades").update(items("1", "2")) == []


async def test_changed_item_is_changed_not_new(store: LibrusStore) -> None:
    """A known id with another snapshot is a change and carries the old snapshot."""
    tracker = Tracker(store, "grades")
    tracker.update(items("1", "2"))

    changes = tracker.update(items("1") + items("2", value="w"))

    assert kinds(changes) == [("changed", "2")]
    assert changes[0].old == {"value": "v"}


async def test_items_of_new_scopes_are_baseline(store: LibrusStore) -> None:
    """A larger timeframe fires nothing for the added months; known months still do."""
    tracker = Tracker(store, "schedule")
    tracker.update(items("1", scope="2026-10"), scopes=["2026-10", "2026-11"])

    changes = tracker.update(
        items("1", scope="2026-10")
        + items("2", scope="2026-11")
        + items("3", "4", scope="2026-12"),
        scopes=["2026-10", "2026-11", "2026-12"],
    )

    assert kinds(changes) == [("new", "2")]


async def test_dropped_scope_is_baseline_again(store: LibrusStore) -> None:
    """Lower then raise the timeframe: the months come back without events."""
    tracker = Tracker(store, "schedule")
    tracker.update(
        items("1", scope="2026-10") + items("2", scope="2026-11"),
        scopes=["2026-10", "2026-11"],
    )
    tracker.update(items("1", scope="2026-10"), scopes=["2026-10"])

    changes = tracker.update(
        items("1", scope="2026-10") + items("2", "3", scope="2026-11"),
        scopes=["2026-10", "2026-11"],
    )

    assert changes == []


async def test_moved_item_is_changed(store: LibrusStore) -> None:
    """An event moved to another covered month is a change."""
    tracker = Tracker(store, "schedule")
    tracker.update(items("1", scope="2026-10"), scopes=["2026-10", "2026-11"])

    changes = tracker.update(
        [TrackedItem("1", {"value": "moved"}, "item 1", "2026-11")],
        scopes=["2026-10", "2026-11"],
    )

    assert kinds(changes) == [("changed", "1")]


async def test_removed_scoped_item_is_new_when_added_again(store: LibrusStore) -> None:
    """A deleted event that is added again is new."""
    tracker = Tracker(store, "schedule")
    tracker.update(items("1", "2", scope="2026-10"), scopes=["2026-10"])
    tracker.update(items("1", scope="2026-10"), scopes=["2026-10"])

    changes = tracker.update(items("1", "2", scope="2026-10"), scopes=["2026-10"])

    assert kinds(changes) == [("new", "2")]


async def test_unscoped_item_that_comes_back_is_not_new(store: LibrusStore) -> None:
    """A message that left the list (smaller count) does not fire when it returns."""
    tracker = Tracker(store, "messages")
    tracker.update(items("3", "2", "1"))
    tracker.update(items("3", "2"))

    assert tracker.update(items("3", "2", "1")) == []


async def test_kept_items_are_capped(
    store: LibrusStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the last MAX_KEPT ids are kept; the oldest are dropped first."""
    monkeypatch.setattr(tracker_module, "MAX_KEPT", 3)
    tracker = Tracker(store, "messages")
    tracker.update(items("1", "2"))
    tracker.update(items("3", "4"))

    assert list(store.data["tracker"]["messages"]["items"]) == ["2", "3", "4"]


async def test_duplicate_id_in_one_poll_is_reported_once(store: LibrusStore) -> None:
    """Two items with one id in a poll give one change."""
    tracker = Tracker(store, "announcements")
    tracker.update(items("1"))

    assert kinds(tracker.update(items("2", "2", "1"))) == [("new", "2")]


async def test_update_schedules_a_save(store: LibrusStore) -> None:
    """Each update asks the store to save."""
    store.async_schedule_save = lambda: setattr(store, "saved", True)

    Tracker(store, "messages").update(items("1"))

    assert store.saved
