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

            async with _cache_lock:
                if cache_key not in _key_locks:
                    _key_locks[cache_key] = asyncio.Lock()
                key_lock = _key_locks[cache_key]

            async with key_lock:
                async with _cache_lock:
                    entry = _cache.get(cache_key)
                    if entry and time.time() - entry[0] < ttl:
                        return entry[1]

                result = await func(*args, **kwargs)

                async with _cache_lock:
                    _cache[cache_key] = (time.time(), result)
                    global _last_refresh_time
                    _last_refresh_time = datetime.now(BKK_TZ)

                return result
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
