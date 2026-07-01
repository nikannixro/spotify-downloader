"""Centralized service singletons using functools.lru_cache."""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import Database
    from plugins.cache import DownloadCache
    from plugins.spotdl import SpotDLBackend
    from utils.rate_limiter import RateLimiter


@cache
def get_db() -> Database:
    """Return the singleton Database instance."""
    from database import Database

    return Database()


@cache
def get_cache() -> DownloadCache:
    """Return the singleton DownloadCache instance."""
    from plugins.cache import DownloadCache

    return DownloadCache()


@cache
def get_spotdl() -> SpotDLBackend:
    """Return the singleton SpotDLBackend instance."""
    from plugins.spotdl import SpotDLBackend

    return SpotDLBackend()


@cache
def get_rate_limiter() -> RateLimiter:
    """Return the singleton RateLimiter instance."""
    from utils.rate_limiter import RateLimiter

    return RateLimiter()


async def close_all() -> None:
    """Close all persistent resources (database connection, etc.)."""
    db = get_db()
    if hasattr(db, "close"):
        await db.close()
