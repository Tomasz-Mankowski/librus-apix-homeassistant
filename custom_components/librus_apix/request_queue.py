"""Request queue shared by all Librus entries of one Home Assistant instance.

- One job at a time. A job is one blocking librus-apix call run in the executor.
- A gap of REQUEST_GAP seconds between two HTTP requests, also inside one job.
- Backoff per server after LibrusUnavailableError: BACKOFF_START, doubled on each
  failure in a row, capped at BACKOFF_MAX. A success clears it.
"""

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.util.hass_dict import HassKey

from .const import BACKOFF_MAX, BACKOFF_START, DOMAIN, REQUEST_GAP
from .exceptions import LibrusUnavailableError

_LOGGER = logging.getLogger(__name__)


@dataclass
class _Backoff:
    failures: int
    until: float


class RequestQueue:
    """Serializes Librus requests and keeps the backoff state."""

    def __init__(
        self,
        hass: HomeAssistant,
        gap: float = REQUEST_GAP,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create an empty queue. ``clock`` drives the backoff timing."""
        self._hass = hass
        self._gap = gap
        self._clock = clock
        self._lock = asyncio.Lock()
        self._next_request = 0.0
        self._backoff: dict[str, _Backoff] = {}

    async def async_run[T](self, host: str, func: Callable[..., T], *args: Any) -> T:
        """Run ``func(*args)`` in the executor once no other job runs.

        Raises LibrusUnavailableError without running the job while ``host`` is in
        backoff. ``retry_after`` of the raised error is the delay until the next try.
        """
        async with self._lock:
            backoff = self._backoff.get(host)
            if backoff and (wait := backoff.until - self._clock()) > 0:
                raise LibrusUnavailableError(
                    f"{host} is in backoff for {wait:.0f} s", retry_after=wait
                )
            try:
                result = await self._hass.async_add_executor_job(func, *args)
            except LibrusUnavailableError as err:
                err.retry_after = self._add_failure(host, err.retry_after)
                raise
            self._backoff.pop(host, None)
            return result

    def _add_failure(self, host: str, server_hint: float | None) -> float:
        """Record a failure for ``host`` and return the new backoff delay."""
        failures = self._backoff[host].failures + 1 if host in self._backoff else 1
        delay = min(BACKOFF_START * 2 ** (failures - 1), BACKOFF_MAX)
        if server_hint:
            delay = min(max(delay, server_hint), BACKOFF_MAX)
        self._backoff[host] = _Backoff(failures, self._clock() + delay)
        _LOGGER.debug("Backoff for %s: %.0f s (failure %d)", host, delay, failures)
        return delay

    @contextmanager
    def request_slot(self) -> Iterator[None]:
        """Wait for the gap before one HTTP request. Runs in the job's thread."""
        if (wait := self._next_request - time.monotonic()) > 0:
            time.sleep(wait)
        try:
            yield
        finally:
            self._next_request = time.monotonic() + self._gap


DATA_REQUEST_QUEUE: HassKey[RequestQueue] = HassKey(f"{DOMAIN}_request_queue")


@callback
def async_get_request_queue(hass: HomeAssistant) -> RequestQueue:
    """Return the request queue of this Home Assistant instance."""
    if (queue := hass.data.get(DATA_REQUEST_QUEUE)) is None:
        queue = hass.data[DATA_REQUEST_QUEUE] = RequestQueue(hass)
    return queue
