import asyncio
import time
import json
import logging
from functools import wraps
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BKK_TZ = ZoneInfo("Asia/Bangkok")
CACHE_TTL = 300  # 5 นาที
FETCH_TIMEOUT = 7.0  # seconds; per logical read (all HTTP hops); loosened until read-retry (P3.1d) lands
LOCK_WAIT_TIMEOUT = 14.0  # seconds; max time parked on a per-key lock (2× FETCH_TIMEOUT for coalescing)

_cache: dict = {}
_key_locks: dict = {}
_cache_lock = asyncio.Lock()
_last_refresh_time: datetime | None = None


def _generate_cache_key(prefix: str, args, kwargs) -> str:
    return f"{prefix}:{json.dumps(args, default=str)}:{json.dumps(kwargs, default=str)}"


def cached(key_prefix: str, ttl: int = CACHE_TTL):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = _generate_cache_key(key_prefix, args, kwargs)

            # Fast path: serve a fresh cache hit without contending for the key lock.
            async with _cache_lock:
                entry = _cache.get(cache_key)
                if entry and time.time() - entry[0] < ttl:
                    return entry[1]

            async with _cache_lock:
                if cache_key not in _key_locks:
                    _key_locks[cache_key] = asyncio.Lock()
                key_lock = _key_locks[cache_key]

            try:
                async with asyncio.timeout(LOCK_WAIT_TIMEOUT):
                    async with key_lock:
                        # Re-check under the lock: a waiter may have refreshed it.
                        async with _cache_lock:
                            entry = _cache.get(cache_key)
                            if entry and time.time() - entry[0] < ttl:
                                return entry[1]

                        result = await asyncio.wait_for(
                            func(*args, **kwargs), timeout=FETCH_TIMEOUT
                        )

                        async with _cache_lock:
                            _cache[cache_key] = (time.time(), result)
                            global _last_refresh_time
                            _last_refresh_time = datetime.now(BKK_TZ)

                        return result
            except TimeoutError:
                logger.warning("Cached fetch timed out (key_prefix=%s)", key_prefix)
                raise
        return wrapper
    return decorator


async def clear_cache():
    async with _cache_lock:
        _cache.clear()
        _key_locks.clear()
    logger.info("Cache cleared")


def get_cache_entries_count() -> int:
    return len(_cache)


def get_last_refresh_time() -> str:
    if _last_refresh_time is None:
        return "Never"
    return _last_refresh_time.strftime("%H:%M:%S")


async def check_and_set_idempotency(key: str, ttl: int = 300) -> bool:
    """
    Checks if an idempotency key exists and is valid.
    If it exists, returns True (meaning duplicate request).
    If it does not exist, sets it and returns False (meaning first time).
    """
    async with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry[0] < ttl:
            return True

        _cache[key] = (time.time(), True)
        global _last_refresh_time
        _last_refresh_time = datetime.now(BKK_TZ)
        return False


async def clear_idempotency(key: str) -> None:
    """Remove an idempotency key so a failed write can be retried later."""
    async with _cache_lock:
        _cache.pop(key, None)
