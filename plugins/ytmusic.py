"""Artist top tracks module — uses Deezer API for reliable top tracks."""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any

from plugins.deezer import DeezerClient

logger = logging.getLogger(__name__)

_deezer = DeezerClient()


def _get_artist_top_tracks_sync(artist_name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Fetch artist top tracks via Deezer (search artist → get top tracks)."""
    try:
        artists = _deezer._search_artists_sync(artist_name, limit=1)
        if not artists:
            return []

        artist_id = artists[0].get("id")
        tracks = _deezer._get_artist_top_tracks_sync(str(artist_id), limit=limit)

        return [
            {
                "title": t.get("title", "Unknown"),
                "artist": t.get("artist", {}).get("name", artist_name),
                "album": t.get("album", {}).get("title", ""),
                "videoId": t.get("id"),
                "duration": t.get("duration", 0),
                "thumbnail": t.get("album", {}).get("cover_medium", ""),
            }
            for t in tracks[:limit]
        ]
    except Exception as exc:
        logger.error("Deezer top tracks error (artist=%s): %s", artist_name, exc)
        return []


async def get_artist_top_tracks(artist_name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Async wrapper for fetching artist top tracks."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(_get_artist_top_tracks_sync, artist_name, limit)
    )
