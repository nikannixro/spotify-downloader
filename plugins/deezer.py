"""Deezer API client for artist search and top tracks."""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEEZER_SEARCH_URL = "https://api.deezer.com/search/artist"
DEEZER_ARTIST_TOP_URL = "https://api.deezer.com/artist/{artist_id}/top"


class DeezerClient:
    """Async wrapper around the Deezer API."""
    def __init__(self) -> None:
        self._search_cache: dict[str, list[dict[str, Any]]] = {}
        self._top_tracks_cache: dict[str, list[dict[str, Any]]] = {}

    def _search_artists_sync(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        cache_key = f"{query}:{limit}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        try:
            response = requests.get(
                DEEZER_SEARCH_URL, params={"q": query, "limit": limit}, timeout=10
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("data", [])
            self._search_cache[cache_key] = results
            return results
        except Exception as exc:
            logger.error("Deezer search error (q=%s): %s", query, exc)
            return []

    async def search_artists(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, functools.partial(self._search_artists_sync, query, limit)
        )

    def _get_artist_top_tracks_sync(self, artist_id: str, limit: int = 10) -> list[dict[str, Any]]:
        cache_key = f"{artist_id}:{limit}"
        if cache_key in self._top_tracks_cache:
            return self._top_tracks_cache[cache_key]

        try:
            url = DEEZER_ARTIST_TOP_URL.format(artist_id=artist_id)
            response = requests.get(url, params={"limit": limit}, timeout=10)
            response.raise_for_status()
            data = response.json()
            tracks = data.get("data", [])
            self._top_tracks_cache[cache_key] = tracks
            return tracks
        except Exception as exc:
            logger.error("Deezer top tracks error (artist_id=%s): %s", artist_id, exc)
            return []

    async def get_artist_top_tracks(self, artist_id: str, limit: int = 10) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, functools.partial(self._get_artist_top_tracks_sync, artist_id, limit)
        )
