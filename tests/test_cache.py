"""
test_cache.py — Unit tests for services/cache.py

Tests:
- cache hit (no re-fetch within TTL)
- cache miss after TTL expires
- clear_cache resets state
- stampede protection (concurrent callers hit fn only once)
"""
import asyncio
import pytest
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
