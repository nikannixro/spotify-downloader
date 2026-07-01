"""Inline search handler — Spotify / Deezer inline query results."""

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

SEARCH_PREFIXES: dict[str, SearchType] = {
    "art:": SearchType.ARTIST,
    "alb:": SearchType.ALBUM,
    "pla:": SearchType.PLAYLIST,
    "trk:": SearchType.TRACK,
}

_deezer_client = DeezerClient()


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
        if await db.get_channels():
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
        if search_type == SearchType.ARTIST:
            data = await _deezer_client.search_artists(term, limit=15)
            if not data:
                await inline_query.answer([])
                return
            results = _build_inline_results(search_type, data)
        else:
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
            results = _build_inline_results(search_type, data)
    except Exception as exc:
        logger.error("Inline search error: %s", exc)
        await inline_query.answer([])
        return

    valid_results = [r for r in results if r.thumb_url]
    await inline_query.answer(valid_results[:20], cache_time=300)


def _build_inline_results(search_type: SearchType, data: Any) -> list[InlineQueryResultArticle]:
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
            for item in data:
                name = item.get("name", "Unknown")
                nb_album = item.get("nb_album", 0)
                nb_fan = item.get("nb_fan", 0)
                thumb = item.get("picture_medium") or item.get("picture")
                link = item.get("link", "")

                out.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=name,
                        description=f"Album number: {nb_album}\nFan number: {nb_fan:,}",
                        thumb_url=thumb,
                        input_message_content=InputTextMessageContent(link),
                    )
                )

        elif search_type == SearchType.ALBUM:
            for item in data["albums"]["items"]:
                artists = ", ".join(a["name"] for a in item["artists"])
                release = item.get("release_date", "?")
                year = release[:4] if release else "?"
                total = item.get("total_tracks", "?")
                images = item["images"]
                thumb = images[0]["url"] if images else None
                out.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=f"💿 {item['name']}",
                        description=f"👤 {artists} | {year} | {total} tracks",
                        thumb_url=thumb,
                        input_message_content=InputTextMessageContent(
                            item["external_urls"]["spotify"]
                        ),
                    )
                )

        elif search_type == SearchType.PLAYLIST:
            for item in data["playlists"]["items"]:
                owner = item["owner"]["display_name"]
                total = item["tracks"]["total"]
                images = item["images"]
                thumb = images[0]["url"] if images else None
                out.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=f"📁 {item['name']}",
                        description=f"By: {owner} | {total} tracks",
                        thumb_url=thumb,
                        input_message_content=InputTextMessageContent(
                            item["external_urls"]["spotify"]
                        ),
                    )
                )
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Result parse error: %s", exc)
    return out
