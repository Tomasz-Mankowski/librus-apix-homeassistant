"""New-item tracking (F16, F17).

A tracker remembers a small snapshot of every item it has seen, in the entry store,
so the state survives restarts.

- First poll (nothing stored yet): every item is recorded; nothing is reported.
- Later polls: an unknown id is "new"; a known id with a different snapshot is
  "changed" (the old snapshot comes with it). Changes keep the order of the input.
- Scopes (for example schedule months): the caller passes the scopes the poll
  covers. Items in a scope that was not covered before are baseline, so a larger
  timeframe fires nothing. Items of covered scopes that are no longer listed are
  forgotten; a scope that is no longer covered is forgotten with its items.
- Without scopes (messages, grades, announcements) items that are no longer
  listed are kept, up to MAX_KEPT, so they do not fire again if they come back
  (for example after a larger message count).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from .store import LibrusStore

MAX_KEPT = 1000

type Snapshot = dict[str, Any]


@dataclass(frozen=True)
class TrackedItem[T]:
    """One item of a poll: id, JSON-serializable snapshot, the item, its scope."""

    item_id: str
    snapshot: Snapshot
    item: T
    scope: str | None = None


@dataclass(frozen=True)
class Change[T]:
    """A new or changed item; ``old`` is the snapshot before a change."""

    kind: Literal["new", "changed"]
    item: T
    item_id: str
    old: Snapshot | None = None


class Tracker[T]:
    """Seen items of one data type of one entry."""

    def __init__(self, store: LibrusStore, name: str) -> None:
        """Keep the state in store.data["tracker"][name]."""
        self._store = store
        self._name = name

    def update(
        self, items: Iterable[TrackedItem[T]], scopes: Iterable[str] | None = None
    ) -> list[Change[T]]:
        """Record the items of a poll and return the new and changed ones."""
        trackers: dict[str, Any] = self._store.data.setdefault("tracker", {})
        state = trackers.get(self._name)
        first_poll = state is None
        known: dict[str, Snapshot] = {} if state is None else state["items"]
        known_scopes = set(state.get("scopes") or []) if state else set()

        changes: list[Change[T]] = []
        current: dict[str, Snapshot] = {}
        for tracked in items:
            if tracked.item_id in current:
                continue
            current[tracked.item_id] = tracked.snapshot
            old = known.get(tracked.item_id)
            if old is None:
                baseline = first_poll or (
                    tracked.scope is not None and tracked.scope not in known_scopes
                )
                if not baseline:
                    changes.append(Change("new", tracked.item, tracked.item_id))
            elif old != tracked.snapshot:
                changes.append(Change("changed", tracked.item, tracked.item_id, old))

        if scopes is not None:
            kept = current
        else:
            kept = {key: value for key, value in known.items() if key not in current}
            kept.update(current)
            kept = dict(list(kept.items())[-MAX_KEPT:])
        trackers[self._name] = {
            "scopes": sorted(scopes) if scopes is not None else None,
            "items": kept,
        }
        self._store.async_schedule_save()
        return changes
