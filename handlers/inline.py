"""Inline search handler — Spotify inline query results."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from pyrogram import Client
from pyrogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from config import is_admin
from handlers.start import _check_membership
from models import SearchType
from plugins.deezer import DeezerClient
from services import get_db
from strings import MAINTENANCE_INLINE, NOT_JOINED_INLINE

logger = logging.getLogger(__name__)

_deezer = DeezerClient()
_DEEZER_SEMAPHORE = asyncio.Semaphore(3)

SEARCH_PREFIXES: dict[str, SearchType] = {
    "artist:": SearchType.ARTIST,
    "album:": SearchType.ALBUM,
    "playlist:": SearchType.PLAYLIST,
    "track:": SearchType.TRACK,
}


@Client.on_inline_query()
async def inline_search(client: Client, inline_query: InlineQuery) -> None:
    """Handle inline queries — search Spotify and Deezer, return results."""
    user_id = inline_query.from_user.id

    if not is_admin(user_id):
        db = get_db()
        if await db.get_setting("maintenance_mode") == "1":
            await inline_query.answer(
                [],
                switch_pm_text=MAINTENANCE_INLINE,
                switch_pm_parameter="maintenance",
            )
            return
        if await db.get_setting("force_join_enabled") == "1":
            not_joined = await _check_membership(client, user_id)
            if not_joined:
                await inline_query.answer(
                    [],
                    switch_pm_text=NOT_JOINED_INLINE,
                    switch_pm_parameter="verify",
                )
                return

    raw = inline_query.query.strip() or "trending"
    search_type = SearchType.TRACK
    term = raw
    for prefix, stype in SEARCH_PREFIXES.items():
        if raw.startswith(prefix):
            search_type = stype
            term = raw[len(prefix) :].strip()
            break

    if not term:
        await inline_query.answer([])
        return

    try:
        from plugins.spotdl import _ensure_spotdl_init
        from spotdl.utils.spotify import SpotifyClient

        _ensure_spotdl_init()
        spotify = SpotifyClient()
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None, lambda: spotify.search(q=term, type=search_type.value, limit=10)
        )
        if not data:
            await inline_query.answer([])
            return
    except Exception as exc:
        logger.error("Inline search error: %s", exc)
        await inline_query.answer([])
        return

    followers_map: dict[str, int] = {}
    playlist_track_counts: dict[str, int | None] = {}
    if search_type == SearchType.ARTIST:
        artist_items = data.get("artists", {}).get("items", [])
        names = [item.get("name", "") for item in artist_items]

        async def _throttled_search(name: str) -> dict[str, Any] | None:
            async with _DEEZER_SEMAPHORE:
                return await _deezer.search_artist_best_match(name, name, limit=5)

        tasks = [_throttled_search(n) if n else asyncio.sleep(0) for n in names]
        deezer_results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(names, deezer_results):
            if not name or isinstance(result, Exception):
                continue
            if result:
                followers_map[name.lower()] = result.get("nb_fan", 0)

    if search_type == SearchType.PLAYLIST:
        items = data.get("playlists", {}).get("items", [])
        ids_to_fetch = []
        for item in items:
            if not item:
                continue
            pid = item.get("id")
            tracks_obj = item.get("tracks") or {}
            if isinstance(tracks_obj, dict) and tracks_obj.get("total") is not None:
                playlist_track_counts[pid] = tracks_obj["total"]
            elif pid:
                ids_to_fetch.append(pid)

        if ids_to_fetch:
            def _fetch_playlist_count(pid: str) -> tuple[str, int | None]:
                try:
                    pl = spotify.playlist(pid, fields="tracks.total")
                    return pid, pl.get("tracks", {}).get("total")
                except Exception:
                    return pid, None

            fetch_tasks = [
                loop.run_in_executor(None, _fetch_playlist_count, pid)
                for pid in ids_to_fetch
            ]
            fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            for r in fetch_results:
                if isinstance(r, Exception):
                    continue
                pid, count = r
                playlist_track_counts[pid] = count

    results = _build_inline_results(
        search_type, data, followers_map,
        user_id=user_id, playlist_track_counts=playlist_track_counts,
    )

    valid_results = [r for r in results if r.thumb_url]
    await inline_query.answer(valid_results[:20], cache_time=300)


def _build_inline_results(
    search_type: SearchType,
    data: Any,
    followers_map: dict[str, int] | None = None,
    user_id: int = 0,
    playlist_track_counts: dict[str, int | None] | None = None,
) -> list[InlineQueryResultArticle]:
    """Build InlineQueryResultArticle list from search data."""
    out: list[InlineQueryResultArticle] = []
    try:
        if search_type == SearchType.TRACK:
            for item in data["tracks"]["items"]:
                artists = ", ".join(a["name"] for a in item["artists"])
                album_name = item["album"]["name"]
                release = item["album"].get("release_date", "?")
                year = release[:4] if release else "?"
                images = item["album"]["images"]
                thumb = images[0]["url"] if images else None
                out.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=f"🎧 {item['name']}",
                        description=f"👤 {artists}\n💿 {album_name} ({year})",
                        thumb_url=thumb,
                        input_message_content=InputTextMessageContent(
                            item["external_urls"]["spotify"]
                        ),
                    )
                )

        elif search_type == SearchType.ARTIST:
            for item in data["artists"]["items"]:
                name = item.get("name", "Unknown")
                followers = (followers_map or {}).get(name.lower(), 0)
                images = item.get("images", [])
                thumb = images[0]["url"] if images else None
                artist_id = item.get("id", "")
                result_id = str(uuid.uuid4())

                out.append(
                    InlineQueryResultArticle(
                        id=result_id,
                        title=name,
                        description=f"👤 Followers: {followers:,}",
                        thumb_url=thumb,
                        input_message_content=InputTextMessageContent(
                            f"https://open.spotify.com/artist/{artist_id}"
                        ),
                    )
                )

        elif search_type == SearchType.ALBUM:
            for item in data["albums"]["items"]:
                artists = ", ".join(a["name"] for a in item["artists"])
                total = item.get("total_tracks", "?")
                images = item["images"]
                thumb = images[0]["url"] if images else None
                out.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=item["name"],
                        description=f"Tracks number: {total}\nArtist: {artists}",
                        thumb_url=thumb,
                        input_message_content=InputTextMessageContent(
                            item["external_urls"]["spotify"]
                        ),
                    )
                )

        elif search_type == SearchType.PLAYLIST:
            for item in data.get("playlists", {}).get("items", []):
                if not item:
                    continue
                owner_obj = item.get("owner") or {}
                if isinstance(owner_obj, dict):
                    owner = owner_obj.get("display_name") or "anonymous"
                else:
                    owner = "anonymous"
                tracks_obj = item.get("tracks") or {}
                total = None
                if isinstance(tracks_obj, dict):
                    total = tracks_obj.get("total")
                if total is None:
                    pid = item.get("id")
                    if pid and playlist_track_counts:
                        total = playlist_track_counts.get(pid)
                    if total is None:
                        total = "?"
                images = item.get("images") or []
                thumb = images[0]["url"] if images else None
                out.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=item["name"],
                        description=f"Tracks number: {total}\nUser: {owner}",
                        thumb_url=thumb,
                        input_message_content=InputTextMessageContent(
                            item["external_urls"]["spotify"]
                        ),
                    )
                )
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        logger.warning("Result parse error: %s", exc)
    return out
