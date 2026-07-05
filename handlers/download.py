"""Download handler — processes Spotify links (track, album, playlist)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from typing import Any

from pyrogram import Client, filters
from pyrogram.types import InputMediaAudio, Message
from spotdl.utils.spotify import SpotifyClient

import plugins.download_manager as download_manager
from config import is_admin
from handlers.start import enforce_membership
from models import AdminState, DownloadResult, TrackMetadata
from plugins.spotdl import _ensure_spotdl_init
from services import get_db, get_rate_limiter, get_spotdl
from strings import (
    ARTIST_DOB_UNKNOWN,
    ARTIST_PROFILE_CAPTION,
    CANCELLED,
    DL_DONE,
    DL_FAILED,
    RATE_LIMITED,
    UNSUPPORTED_LINK,
)
from utils.helpers import SpotifyLinkType, download_cover_bytes, parse_spotify_link
from utils.keyboards import artist_top_button, cancel_download_keyboard, main_keyboard

URL_REGEX: re.Pattern[str] = re.compile(r"https?://\S+")
AUDIO_BATCH_SIZE: int = 10

logger = logging.getLogger(__name__)

_artist_tracks_cache: dict[int, list[dict[str, Any]]] = {}


@Client.on_message(filters.text & filters.private & ~filters.command(["start", "cancel", "admin"]))
async def handle_text_message(client: Client, message: Message) -> None:
    """Route text messages: admin conversation states take priority, then Spotify links."""
    if not message.from_user:
        return
    user_id = message.from_user.id

    from handlers.states import get_state

    state = get_state(user_id)
    if state is not None:
        await _route_admin_text(client, message, state)
        return

    text = message.text or ""

    if text.startswith("dl_track:"):
        track_id = text.split(":", 1)[1].strip()
        if track_id:
            await message.delete()
            await _download_inline_track(client, message, user_id, track_id)
            return

    if message.via_bot:
        parsed = parse_spotify_link(text)
        if parsed and parsed[0] == SpotifyLinkType.TRACK:
            await message.delete()
            await _download_inline_track(client, message, user_id, parsed[1])
            return

    await handle_spotify_link(client, message)


async def _route_admin_text(client: Client, message: Message, state: AdminState) -> None:
    """Route text input to the correct admin handler based on conversation state."""
    from handlers.admin import (
        admin_back_to_main_handler,
        h_broadcast_handler,
        h_chan_id_handler,
        h_join_msg_handler,
        h_log_channel_handler,
        h_rate_limit_handler,
        h_rate_window_handler,
        h_start_msg_handler,
    )
    from handlers.states import clear_state, set_state

    new_state = None
    if state == AdminState.WAIT_START_MSG:
        new_state = await h_start_msg_handler(client, message)
    elif state == AdminState.WAIT_BROADCAST:
        new_state = await h_broadcast_handler(client, message)
    elif state == AdminState.WAIT_CHAN_ID:
        new_state = await h_chan_id_handler(client, message)
    elif state == AdminState.WAIT_RATE_LIMIT:
        new_state = await h_rate_limit_handler(client, message)
    elif state == AdminState.WAIT_RATE_WINDOW:
        new_state = await h_rate_window_handler(client, message)
    elif state == AdminState.WAIT_JOIN_MSG:
        new_state = await h_join_msg_handler(client, message)
    elif state == AdminState.WAIT_LOG_CHANNEL:
        new_state = await h_log_channel_handler(client, message)
    elif state == AdminState.ADMIN_CHOOSE:
        if message.text and message.text.strip() == "🔙 بازگشت":
            new_state = await admin_back_to_main_handler(client, message)
        else:
            return

    if new_state is not None and new_state < 0:
        clear_state(message.from_user.id)
    elif new_state is not None:
        set_state(message.from_user.id, new_state)


async def handle_spotify_link(client: Client, message: Message) -> None:
    """Process a message that may contain a Spotify URL."""
    if not message.text:
        return
    if not message.from_user:
        return
    user_id = message.from_user.id

    parsed = parse_spotify_link(message.text)
    if not parsed:
        if URL_REGEX.search(message.text):
            if "deezer.com" in message.text:
                return
            await message.reply_text(UNSUPPORTED_LINK)
        else:
            db = get_db()
            text = await db.get_setting("start_message")
            await message.reply_text(
                text=text,
                reply_markup=main_keyboard(is_admin(user_id)),
            )
        return

    link_type, resource_id = parsed

    if link_type == SpotifyLinkType.ARTIST:
        if not await enforce_membership(client, message):
            return
        await _show_artist_profile(client, message, user_id, resource_id)
        return

    if not await enforce_membership(client, message):
        return

    rate_limiter = get_rate_limiter()
    if not is_admin(user_id) and await rate_limiter.is_limited(user_id):
        window = await rate_limiter.window_seconds()
        await message.reply_text(RATE_LIMITED.format(window=window))
        return

    download_manager.clear_cancel_flag(user_id)

    task = asyncio.current_task()
    try:
        if link_type == SpotifyLinkType.TRACK:
            await _download_single_track(client, message, user_id, resource_id, task)
        elif link_type == SpotifyLinkType.ALBUM:
            await _download_collection(
                client,
                message,
                user_id,
                get_spotdl().get_album_songs(f"https://open.spotify.com/album/{resource_id}"),
                is_album=True,
                task=task,
            )
        elif link_type == SpotifyLinkType.PLAYLIST:
            await _download_collection(
                client,
                message,
                user_id,
                get_spotdl().get_playlist_songs(f"https://open.spotify.com/playlist/{resource_id}"),
                is_album=False,
                task=task,
            )
    finally:
        if task:
            download_manager.unregister(user_id, task)


async def _download_single_track(
    client: Client, message: Message, user_id: int, track_id: str, task: asyncio.Task | None = None
) -> None:
    """Download a single Spotify track with full message flow."""
    spotdl = get_spotdl()
    url = f"https://open.spotify.com/track/{track_id}"

    task_id = download_manager.register(user_id, task) if task else 0
    status_msg = await message.reply_text(
        "⬇️ Downloading...",
        reply_markup=cancel_download_keyboard(user_id, task_id),
    )

    try:
        result = await spotdl.download_track(url, user_id)
    except asyncio.CancelledError:
        logger.info("Download cancelled for user %d track %s", user_id, track_id)
        download_manager.cleanup_user_files(user_id)
        with contextlib.suppress(Exception):
            await status_msg.edit_text(CANCELLED)
        return
    except Exception:
        logger.exception("Download failed for user %d track %s", user_id, track_id)
        with contextlib.suppress(Exception):
            await status_msg.edit_text(DL_FAILED)
        return

    if download_manager.is_cancelled(user_id):
        download_manager.clear_cancel_flag(user_id)
        download_manager.cleanup_user_files(user_id)
        with contextlib.suppress(Exception):
            await status_msg.edit_text(CANCELLED)
        return

    if not result.success or not result.metadata:
        with contextlib.suppress(Exception):
            await status_msg.edit_text(DL_FAILED)
        return

    with contextlib.suppress(Exception):
        await status_msg.delete()

    db = get_db()
    await db.log_download(user_id, result.metadata.track_id, f"{result.metadata.artists} - {result.metadata.name}")
    photo_msg = await _send_track(message, result)
    target = photo_msg or message
    with contextlib.suppress(Exception):
        await target.reply_text(DL_DONE)


async def _download_inline_track(
    client: Client, message: Message, user_id: int, track_id: str
) -> None:
    """Download track from inline search — sends audio only, no caption."""
    from utils.helpers import download_cover_bytes

    spotdl = get_spotdl()
    url = f"https://open.spotify.com/track/{track_id}"

    task = asyncio.current_task()
    task_id = download_manager.register(user_id, task) if task else 0
    status_msg = await client.send_message(
        chat_id=user_id,
        text="⬇️ Downloading...",
        reply_markup=cancel_download_keyboard(user_id, task_id),
    )
    try:
        result = await spotdl.download_track(url, user_id)
    except asyncio.CancelledError:
        logger.info("Inline download cancelled for user %d track %s", user_id, track_id)
        download_manager.cleanup_user_files(user_id)
        with contextlib.suppress(Exception):
            await status_msg.edit_text(CANCELLED)
        return
    except Exception:
        logger.exception("Inline download failed for user %d track %s", user_id, track_id)
        with contextlib.suppress(Exception):
            await status_msg.edit_text(DL_FAILED)
        return

    if download_manager.is_cancelled(user_id):
        download_manager.clear_cancel_flag(user_id)
        download_manager.cleanup_user_files(user_id)
        with contextlib.suppress(Exception):
            await status_msg.edit_text(CANCELLED)
        return

    if not result.success or not result.metadata:
        with contextlib.suppress(Exception):
            await status_msg.edit_text(DL_FAILED)
        return

    with contextlib.suppress(Exception):
        await status_msg.delete()

    metadata = result.metadata
    thumbnail = None
    if metadata.cover_url:
        cover_data = await download_cover_bytes(metadata.cover_url)
        if cover_data:
            from io import BytesIO

            thumbnail = BytesIO(cover_data)

    duration = metadata.duration_ms // 1000 if metadata.duration_ms else None
    try:
        await client.send_audio(
            chat_id=user_id,
            audio=result.file_path,
            title=metadata.name,
            performer=metadata.artists,
            duration=duration,
            thumb=thumbnail,
        )
    except Exception as exc:
        logger.warning("Failed to send inline audio: %s", exc)

    db = get_db()
    await db.log_download(user_id, metadata.track_id, f"{metadata.artists} - {metadata.name}")


async def _download_collection(
    client: Client,
    message: Message,
    user_id: int,
    get_info_coro,
    is_album: bool,
    task: asyncio.Task | None = None,
) -> None:
    """Download an album or playlist."""
    try:
        info, songs = await get_info_coro
    except asyncio.CancelledError:
        download_manager.cleanup_user_files(user_id)
        await message.reply_text(CANCELLED)
        return
    except Exception:
        logger.exception("Failed to fetch collection info for user %d", user_id)
        await message.reply_text(DL_FAILED)
        return

    if not songs:
        await message.reply_text(DL_FAILED)
        return

    await _send_collection_info(message, info, is_album=is_album)

    task_id = download_manager.register(user_id, task) if task else 0
    status_msg = await message.reply_text(
        "⬇️ Downloading...",
        reply_markup=cancel_download_keyboard(user_id, task_id),
    )

    spotdl = get_spotdl()
    results: list[DownloadResult] = []

    for i, song in enumerate(songs, 1):
        if download_manager.is_cancelled(user_id):
            download_manager.clear_cancel_flag(user_id)
            download_manager.cleanup_user_files(user_id)
            with contextlib.suppress(Exception):
                await status_msg.edit_text(CANCELLED)
            return

        try:
            result = await spotdl.download_song(song, user_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Download failed for track %s: %s", song.song_id, exc)
            continue

        if result.success and result.metadata:
            db = get_db()
            await db.log_download(user_id, result.metadata.track_id, f"{result.metadata.artists} - {result.metadata.name}")
            results.append(result)

    with contextlib.suppress(Exception):
        await status_msg.delete()

    for i in range(0, len(results), AUDIO_BATCH_SIZE):
        batch = results[i : i + AUDIO_BATCH_SIZE]
        try:
            await _send_audio_batch(message, batch)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Failed to send audio batch: %s", exc)

    with contextlib.suppress(Exception):
        await message.reply_text(DL_DONE)


async def _send_collection_info(
    message: Message,
    info: dict[str, Any] | None,
    is_album: bool,
) -> Message | None:
    """Send album/playlist cover art with caption."""
    if not info:
        return None

    if is_album:
        name = info.get("name", "Unknown Album")
        artists = ", ".join(a["name"] for a in info.get("artists", []))
        cover_url = info["images"][0]["url"] if info.get("images") else None
        release_date = info.get("release_date", "")
        tracks_count = info.get("total_tracks", 0)
        caption = f"{artists} - {name}\n\nDate: {release_date}\nTracks: {tracks_count}"
    else:
        name = info.get("name", "Unknown Playlist")
        cover_url = info["images"][0]["url"] if info.get("images") else None
        tracks_count = info.get("tracks", {}).get("total", 0)
        caption = f"{name}\n\nTracks: {tracks_count}"

    try:
        if cover_url:
            return await message.reply_photo(cover_url, caption=caption)
        return await message.reply_text(caption)
    except Exception:
        return None


async def _send_audio_batch(message: Message, results: list[DownloadResult]) -> None:
    """Send a batch of audio files."""
    if not results:
        return
    valid = [r for r in results if r.file_path and os.path.exists(r.file_path) and r.metadata]
    if not valid:
        return

    if len(valid) == 1:
        r = valid[0]
        await _send_single_audio(message, r)
        return

    media: list[InputMediaAudio] = []
    for r in valid:
        duration = r.metadata.duration_ms // 1000 if r.metadata.duration_ms else None
        media.append(
            InputMediaAudio(
                media=r.file_path,
                title=r.metadata.name,
                performer=r.metadata.artists,
                duration=duration,
            )
        )
    if media:
        try:
            await message.reply_media_group(media)
        except Exception as exc:
            logger.warning("Failed to send media group: %s", exc)


async def _send_track(message: Message, result: DownloadResult) -> Message | None:
    """Send a single track: cover photo then audio. Returns the cover/caption message."""
    metadata = result.metadata
    if not metadata:
        return None

    caption = _build_track_caption(metadata)
    photo_msg = None
    with contextlib.suppress(Exception):
        if metadata.cover_url:
            photo_msg = await message.reply_photo(metadata.cover_url, caption=caption)
        else:
            photo_msg = await message.reply_text(caption)

    await asyncio.sleep(4)

    await _send_single_audio(message, result)
    return photo_msg


async def _send_single_audio(message: Message, result: DownloadResult) -> None:
    """Send a single audio file to the user."""
    metadata = result.metadata
    if not metadata or not result.file_path or not os.path.exists(result.file_path):
        return

    thumbnail = None
    if metadata.cover_url:
        cover_data = await download_cover_bytes(metadata.cover_url)
        if cover_data:
            from io import BytesIO

            thumbnail = BytesIO(cover_data)

    duration = metadata.duration_ms // 1000 if metadata.duration_ms else None

    try:
        await message.reply_audio(
            result.file_path,
            title=metadata.name,
            performer=metadata.artists,
            duration=duration,
            thumb=thumbnail,
        )
    except Exception as exc:
        logger.warning("Failed to send audio file: %s", exc)


def _build_track_caption(metadata: TrackMetadata) -> str:
    """Build caption for track info message."""
    lines = [
        f"{metadata.artists} - {metadata.name}",
        "",
        f"Release Date: {metadata.release_date}",
    ]
    return "\n".join(lines)


async def _get_artist_wiki_info(artist_name: str) -> dict[str, str]:
    """Fetch real name and DOB from Wikipedia with suffix fallback."""
    import re as _re

    result = {"real_name": "", "dob": ARTIST_DOB_UNKNOWN}
    suffixes = ["", " (rapper)", " (singer)", " (musician)", " (band)"]

    try:
        loop = asyncio.get_running_loop()

        def _search_and_fetch(query: str) -> str | None:
            import requests as req

            headers = {"User-Agent": "SpotifyDownloader/1.0"}

            search_resp = req.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": 1,
                },
                headers=headers,
                timeout=10,
            )
            search_resp.raise_for_status()
            results = (
                search_resp.json().get("query", {}).get("search", [])
            )
            if not results:
                return None

            page_title = results[0].get("title")

            content_resp = req.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "titles": page_title,
                    "prop": "revisions",
                    "rvprop": "content",
                    "format": "json",
                    "rvlimit": 1,
                },
                headers=headers,
                timeout=10,
            )
            content_resp.raise_for_status()
            pages = (
                content_resp.json().get("query", {}).get("pages", {})
            )
            page = next(iter(pages.values()), {})
            revisions = page.get("revisions", [])
            if not revisions:
                return None

            return revisions[0].get("*", "")

        def _extract_birth_name(wikitext: str) -> str:
            match = _re.search(
                r"(?i)birth_name\s*=\s*(.+?)(?:\n|$)", wikitext
            )
            if not match:
                return ""
            name = match.group(1).strip()
            name = _re.sub(r"\[\[([^|\]]*?\|)?([^\]]+?)\]\]", r"\2", name)
            name = _re.sub(r"\{\{lang\|[^|]*\|([^}]*)\}\}", r"\1", name)
            name = _re.sub(r"\{\{[^}]*\}\}", "", name)
            name = _re.sub(r"'''?", "", name)
            name = _re.sub(r"<[^>]+>", "", name)
            return name.strip()

        def _extract_dob(wikitext: str) -> str:
            patterns = [
                (r"(?i)birth_date\s*=\s*\{\{[Bb]irth date(?:\s+and\s+age)?\|(\d{4})\|(\d{1,2})\|(\d{1,2})", 3),
                (r"(?i)birth_date\s*=\s*\{\{[Bb]IRTH_date\|(\d{4})\|(\d{1,2})\|(\d{1,2})", 3),
                (r"(?i)birth_date\s*=\s*\{\{[Bb]irth date and age\|df\=yes\|(\d{4})\|(\d{1,2})\|(\d{1,2})", 3),
                (r"(?i)birth_date\s*=\s*(\d{4})-(\d{1,2})-(\d{1,2})", 3),
                (r"(?i)birth_date\s*=\s*(\w+ \d{1,2},? \d{4})", 1),
                (r"(?i)born\s*=\s*\{\{[Bb]irth date(?:\s+and\s+age)?\|(\d{4})\|(\d{1,2})\|(\d{1,2})", 3),
                (r"(?i)born\s*=\s*(\d{4})-(\d{1,2})-(\d{1,2})", 3),
                (r"(?i)born\s*=\s*(\w+ \d{1,2},? \d{4})", 1),
            ]
            for pattern, num_groups in patterns:
                match = _re.search(pattern, wikitext)
                if match:
                    groups = match.groups()
                    if num_groups == 3 and groups[0].isdigit():
                        return f"{groups[0]}-{int(groups[1]):02d}-{int(groups[2]):02d}"
                    elif num_groups == 1:
                        return groups[0]
            return ARTIST_DOB_UNKNOWN

        for suffix in suffixes:
            query = artist_name + suffix
            wikitext = await loop.run_in_executor(
                None, _search_and_fetch, query
            )
            if not wikitext:
                continue

            real_name = _extract_birth_name(wikitext)
            dob = _extract_dob(wikitext)

            if real_name:
                result["real_name"] = real_name
            if dob != ARTIST_DOB_UNKNOWN:
                result["dob"] = dob

            if result["real_name"] and result["dob"] != ARTIST_DOB_UNKNOWN:
                return result

        return result
    except Exception as exc:
        logger.warning("Wikipedia lookup failed for %s: %s", artist_name, exc)
        return result


async def _show_artist_profile(
    client: Client, message: Message, user_id: int, artist_id: str
) -> None:
    """Show artist profile with top tracks for download."""
    from plugins.ytmusic import get_artist_top_tracks

    _ensure_spotdl_init()
    spotify = SpotifyClient()

    try:
        loop = asyncio.get_running_loop()

        def _get_artist_info():
            return spotify.artist(artist_id)

        artist_info = await loop.run_in_executor(None, _get_artist_info)
    except Exception as exc:
        logger.error("Failed to fetch artist info: %s", exc)
        with contextlib.suppress(Exception):
            await client.send_message(user_id, DL_FAILED)
        return

    artist_name = artist_info.get("name", "Unknown")
    images = artist_info.get("images", [])
    cover_url = images[0]["url"] if images else None

    wiki_info = await _get_artist_wiki_info(artist_name)
    real_name = wiki_info["real_name"] or artist_name
    dob = wiki_info["dob"]

    top_tracks_data = await get_artist_top_tracks(artist_name, limit=10)

    caption = ARTIST_PROFILE_CAPTION.format(
        real_name=real_name,
        stage_name=artist_name,
        dob=dob,
    )

    _artist_tracks_cache[user_id] = top_tracks_data[:10]
    kb = artist_top_button(user_id) if top_tracks_data else None

    if cover_url:
        await client.send_photo(
            chat_id=user_id,
            photo=cover_url,
            caption=caption,
            reply_markup=kb,
        )
    else:
        await client.send_message(
            chat_id=user_id,
            text=caption,
            reply_markup=kb,
        )
