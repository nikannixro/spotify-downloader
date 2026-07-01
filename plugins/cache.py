"""Download cache — stores and reuses previously downloaded tracks."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Any

from config import cfg
from models import CacheEntry
from services import get_db

logger = logging.getLogger(__name__)


class DownloadCache:
    """Manages cached downloaded audio files."""

    def __init__(self, cache_dir: str = "cache") -> None:
        self._dir: str = cache_dir
        self._max_age_days: int = cfg.CACHE_MAX_DAYS
        self._max_size_mb: int = cfg.CACHE_MAX_MB
        os.makedirs(self._dir, exist_ok=True)

    async def get(self, track_id: str) -> CacheEntry | None:
        """Return a cached entry if it still exists on disk, otherwise evict and miss."""
        db = get_db()
        entry = await db.cache_get(track_id)
        if entry and os.path.exists(entry["file_path"]):
            logger.info("Cache hit for track %s", track_id)
            return CacheEntry(
                track_id=entry["track_id"],
                file_path=entry["file_path"],
                filename=entry["filename"],
                created_at=entry["created_at"],
                size_bytes=entry["size_bytes"],
            )
        if entry:
            await db.cache_remove(track_id)
        logger.info("Cache miss for track %s", track_id)
        return None

    async def put(self, track_id: str, file_path: str, filename: str) -> CacheEntry:
        """Copy a file into the cache directory and record it in the database."""
        cache_path = os.path.join(self._dir, f"{track_id}.flac")
        shutil.copy2(file_path, cache_path)
        size = os.path.getsize(cache_path)
        db = get_db()
        await db.cache_put(track_id, cache_path, filename, size)
        logger.info("Cached track %s (%d bytes)", track_id, size)
        return CacheEntry(
            track_id=track_id,
            file_path=cache_path,
            filename=filename,
            created_at="",
            size_bytes=size,
        )

    async def remove(self, track_id: str) -> None:
        """Delete a cached file from disk and the database."""
        db = get_db()
        entry = await db.cache_get(track_id)
        if entry:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._safe_remove, entry["file_path"])
            except OSError as exc:
                logger.warning(
                    "Failed to remove cache file %s: %s",
                    entry["file_path"],
                    exc,
                )
        await db.cache_remove(track_id)

    @staticmethod
    def _safe_remove(path: str) -> None:
        """Remove a file if it exists. Intended for use in a thread executor."""
        if os.path.exists(path):
            os.remove(path)

    async def cleanup(self) -> int:
        """Remove stale and oversized cache entries; return count removed."""
        removed = await get_db().cache_cleanup(self._max_age_days, self._max_size_mb)
        if removed:
            logger.info("Cache cleanup: removed %d entries", removed)
        return removed

    async def get_stats(self) -> dict[str, Any]:
        """Return cache statistics (total_files, total_size_bytes)."""
        return await get_db().cache_get_stats()

    def get_dir(self) -> str:
        return self._dir
