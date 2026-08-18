"""
test_cache.py — Unit tests for services/cache.py

Tests:
- cache hit (no re-fetch within TTL)
- cache miss after TTL expires
- clear_cache resets state
- stampede protection (concurrent callers hit fn only once)
"""
import asyncio
import time

import pytest

from services import cache as cache_module
from services.cache import cached, clear_cache, get_cache_entries_count


@pytest.fixture(autouse=True)
async def reset_cache():
    """Ensure clean cache state for every test."""
    await clear_cache()
    yield
    await clear_cache()


async def test_cache_hit():
    """Within TTL, the underlying function should only be called once."""
    call_count = 0

    @cached("test_hit")
    async def expensive_fn():
        nonlocal call_count
        call_count += 1
        return {"value": 42}

    result1 = await expensive_fn()
    result2 = await expensive_fn()

    assert result1 == result2 == {"value": 42}
    assert call_count == 1, "Function should be called only once within TTL"


async def test_cache_miss_after_ttl():
    """After TTL expires, the underlying function should be re-called."""
    call_count = 0

    @cached("test_ttl", ttl=0)  # TTL = 0 → always expired
    async def fn():
        nonlocal call_count
        call_count += 1
        return call_count

    await fn()
    await fn()

    assert call_count == 2, "Function should be called again after TTL=0"


async def test_clear_cache():
    """After clear_cache, the function should be re-fetched."""
    call_count = 0

    @cached("test_clear")
    async def fn():
        nonlocal call_count
        call_count += 1
        return "data"

    await fn()
    assert get_cache_entries_count() >= 1

    await clear_cache()
    assert get_cache_entries_count() == 0

    await fn()
    assert call_count == 2, "Function should be called again after cache clear"


async def test_stampede_protection():
    """Concurrent callers should only trigger the underlying function once."""
    call_count = 0

    @cached("test_stampede")
    async def slow_fn():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)  # Simulate slow I/O
        return "result"

    results = await asyncio.gather(slow_fn(), slow_fn(), slow_fn())

    assert all(r == "result" for r in results)
    assert call_count == 1, "Stampede protection: fn should be called only once"


# ── Timeout & lock-behavior coverage (P3.1b) ──────────────────────────────────


async def test_fetch_timeout_raises(monkeypatch):
    """A fetch slower than FETCH_TIMEOUT raises TimeoutError instead of hanging."""
    monkeypatch.setattr(cache_module, "FETCH_TIMEOUT", 0.05)
    monkeypatch.setattr(cache_module, "LOCK_WAIT_TIMEOUT", 1.0)

    @cached("test_fetch_timeout")
    async def slow_fn():
        await asyncio.sleep(0.3)  # much longer than the patched FETCH_TIMEOUT
        return "data"

    with pytest.raises(TimeoutError):
        await slow_fn()


async def test_lock_released_after_fetch_timeout(monkeypatch):
    """After a fetch timeout, the per-key lock must not leak: a later caller proceeds."""
    monkeypatch.setattr(cache_module, "FETCH_TIMEOUT", 0.05)
    monkeypatch.setattr(cache_module, "LOCK_WAIT_TIMEOUT", 1.0)

    state = {"sleep": 0.3, "calls": 0}

    @cached("test_lock_release")
    async def fetch():
        state["calls"] += 1
        await asyncio.sleep(state["sleep"])
        return "data"

    with pytest.raises(TimeoutError):
        await fetch()
    assert state["calls"] == 1

    # The first fetch timed out, so the cache is still empty. A second caller
    # must be able to acquire the (released) lock and complete. If the lock
    # leaked, it would park until LOCK_WAIT_TIMEOUT and this outer guard would
    # raise instead of returning the result.
    state["sleep"] = 0.0
    result = await asyncio.wait_for(fetch(), timeout=0.3)
    assert result == "data"
    assert state["calls"] == 2


async def test_lock_wait_timeout_fires(monkeypatch):
    """A waiter parked behind a held per-key lock times out instead of waiting forever."""
    monkeypatch.setattr(cache_module, "LOCK_WAIT_TIMEOUT", 0.1)
    monkeypatch.setattr(cache_module, "FETCH_TIMEOUT", 5.0)

    key = cache_module._generate_cache_key("test_lock_wait", (), {})
    held_lock = asyncio.Lock()
    await held_lock.acquire()  # "fake holder" holds the per-key lock indefinitely
    cache_module._key_locks[key] = held_lock

    @cached("test_lock_wait")
    async def fetch():
        return "data"

    try:
        with pytest.raises(TimeoutError):
            await fetch()
    finally:
        held_lock.release()


async def test_coalescing_with_timeouts_configured(monkeypatch):
    """Concurrent callers still share a single fetch when timeouts exist but are not hit."""
    monkeypatch.setattr(cache_module, "FETCH_TIMEOUT", 0.2)
    monkeypatch.setattr(cache_module, "LOCK_WAIT_TIMEOUT", 1.0)

    call_count = 0

    @cached("test_coalescing_timeouts")
    async def slow_fn():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)  # faster than both patched timeouts
        return "result"

    results = await asyncio.gather(slow_fn(), slow_fn(), slow_fn())

    assert all(r == "result" for r in results)
    assert call_count == 1


async def test_prelock_fast_path_bypasses_key_lock():
    """A fresh cache hit is served without ever creating the per-key lock."""
    key = cache_module._generate_cache_key("test_fast_path", (), {})
    cache_module._cache[key] = (time.time(), "cached_value")

    calls = 0

    @cached("test_fast_path")
    async def fetch():
        nonlocal calls
        calls += 1
        return "fetched_value"

    result = await fetch()

    assert result == "cached_value"
    assert calls == 0
    assert key not in cache_module._key_locks
