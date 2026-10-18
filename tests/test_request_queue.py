"""Tests for the shared request queue."""

import asyncio
from itertools import pairwise
import time

from homeassistant.core import HomeAssistant
import pytest

from custom_components.librus_apix.exceptions import LibrusUnavailableError
from custom_components.librus_apix.request_queue import (
    RequestQueue,
    async_get_request_queue,
)


class FakeClock:
    """Monotonic clock moved by the test."""

    def __init__(self) -> None:
        """Start at an arbitrary time."""
        self.now = 1000.0

    def __call__(self) -> float:
        """Return the current time."""
        return self.now


def _refused(retry_after: float | None = None) -> None:
    raise LibrusUnavailableError("refused", retry_after=retry_after)


async def _fail(queue: RequestQueue, host: str, hint: float | None = None) -> float:
    """Run a refused job and return the backoff delay."""
    with pytest.raises(LibrusUnavailableError) as exc:
        await queue.async_run(host, _refused, hint)
    return exc.value.retry_after


async def test_one_queue_per_instance(hass: HomeAssistant) -> None:
    """All entries get the same queue."""
    assert async_get_request_queue(hass) is async_get_request_queue(hass)


async def test_jobs_run_one_at_a_time_with_gap(hass: HomeAssistant) -> None:
    """Jobs never overlap and requests keep the gap."""
    queue = RequestQueue(hass, gap=0.2)
    spans: list[tuple[float, float]] = []

    def job() -> None:
        with queue.request_slot():
            start = time.monotonic()
            time.sleep(0.05)
            spans.append((start, time.monotonic()))

    await asyncio.gather(*(queue.async_run(host, job) for host in "abab"))

    assert len(spans) == 4
    for (_, end), (start, _) in pairwise(sorted(spans)):
        assert start - end >= 0.19


async def test_backoff_grows_and_is_capped(hass: HomeAssistant) -> None:
    """Each failure in a row doubles the delay up to 2 hours."""
    clock = FakeClock()
    queue = RequestQueue(hass, gap=0, clock=clock)

    delays = []
    for _ in range(7):
        delays.append(await _fail(queue, "a"))
        clock.now += delays[-1] + 1

    assert delays == [300, 600, 1200, 2400, 4800, 7200, 7200]


async def test_backoff_refuses_without_running_the_job(hass: HomeAssistant) -> None:
    """During backoff the job does not run; other servers are not affected."""
    clock = FakeClock()
    queue = RequestQueue(hass, gap=0, clock=clock)
    await _fail(queue, "a")
    calls: list[str] = []

    clock.now += 100
    with pytest.raises(LibrusUnavailableError) as exc:
        await queue.async_run("a", calls.append, "a")
    await queue.async_run("b", calls.append, "b")

    assert exc.value.retry_after == pytest.approx(200)
    assert calls == ["b"]


async def test_success_clears_backoff(hass: HomeAssistant) -> None:
    """After a success the next failure starts again at the first delay."""
    clock = FakeClock()
    queue = RequestQueue(hass, gap=0, clock=clock)
    await _fail(queue, "a")
    clock.now += 301

    assert await queue.async_run("a", str.upper, "ok") == "OK"
    assert await _fail(queue, "a") == 300


@pytest.mark.parametrize(("hint", "expected"), [(900, 900), (60, 300), (99999, 7200)])
async def test_server_retry_after_hint(
    hass: HomeAssistant, hint: float, expected: float
) -> None:
    """A longer Retry-After from the server wins, still capped at 2 hours."""
    queue = RequestQueue(hass, gap=0, clock=FakeClock())

    assert await _fail(queue, "a", hint) == expected
