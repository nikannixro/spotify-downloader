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

import plugins.download_manager as download_manager
from config import is_admin
from handlers.start import enforce_membership
from models import AdminState, DownloadResult, TrackMetadata
from services import get_db, get_rate_limiter, get_spotdl
from strings import (
    CANCELLED_FA,
    DL_DONE,
    DL_FAILED,
    RATE_LIMITED,
    UNSUPPORTED_LINK,
)
from utils.helpers import SpotifyLinkType, download_cover_bytes, parse_spotify_link
from utils.keyboards import cancel_download_keyboard, main_keyboard

URL_REGEX: re.Pattern[str] = re.compile(r"https?://\S+")
AUDIO_BATCH_SIZE: int = 10

logger = logging.getLogger(__name__)


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
    if task:
        download_manager.register(user_id, task)
    try:
        if link_type == SpotifyLinkType.TRACK:
            await _download_single_track(client, message, user_id, resource_id)
        elif link_type == SpotifyLinkType.ALBUM:
            await _download_collection(
                client,
                message,
                user_id,
                get_spotdl().get_album_songs(f"https://open.spotify.com/album/{resource_id}"),
                is_album=True,
            )
        elif link_type == SpotifyLinkType.PLAYLIST:
            await _download_collection(
                client,
                message,
                user_id,
                get_spotdl().get_playlist_songs(f"https://open.spotify.com/playlist/{resource_id}"),
                is_album=False,
            )
    finally:
        if task:
            download_manager.unregister(user_id, task)


async def _download_single_track(
    client: Client, message: Message, user_id: int, track_id: str
) -> None:
    """Download a single Spotify track with full message flow."""
    spotdl = get_spotdl()
    url = f"https://open.spotify.com/track/{track_id}"

    status_msg = await message.reply_text(
        "⬇️ Downloading...",
        reply_markup=cancel_download_keyboard(user_id),
    )

    try:
        result = await spotdl.download_track(url, user_id)
    except asyncio.CancelledError:
        logger.info("Download cancelled for user %d track %s", user_id, track_id)
        download_manager.cleanup_user_files(user_id)
        with contextlib.suppress(Exception):
            await status_msg.edit_text(CANCELLED_FA)
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
            await status_msg.edit_text(CANCELLED_FA)
        return

    if not result.success or not result.metadata:
        with contextlib.suppress(Exception):
            await status_msg.edit_text(DL_FAILED)
        return

    with contextlib.suppress(Exception):
        await status_msg.delete()

    await _send_track(message, result)
    with contextlib.suppress(Exception):
        await message.reply_text(DL_DONE)


async def _download_collection(
    client: Client,
    message: Message,
    user_id: int,
    get_info_coro,
    is_album: bool,
) -> None:
    """Download an album or playlist."""
    try:
        info, songs = await get_info_coro
    except asyncio.CancelledError:
        download_manager.cleanup_user_files(user_id)
        await message.reply_text(CANCELLED_FA)
        return
    except Exception:
        logger.exception("Failed to fetch collection info for user %d", user_id)
        await message.reply_text(DL_FAILED)
        return

    if not songs:
        await message.reply_text(DL_FAILED)
        return

    await _send_collection_info(message, info, is_album=is_album)

    status_msg = await message.reply_text(
        "⬇️ Downloading...",
        reply_markup=cancel_download_keyboard(user_id),
    )

    spotdl = get_spotdl()
    results: list[DownloadResult] = []

    for i, song in enumerate(songs, 1):
        if download_manager.is_cancelled(user_id):
            download_manager.clear_cancel_flag(user_id)
            download_manager.cleanup_user_files(user_id)
            with contextlib.suppress(Exception):
                await status_msg.edit_text(CANCELLED_FA)
            return

        try:
            result = await spotdl.download_song(song, user_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Download failed for track %s: %s", song.song_id, exc)
            continue

        if result.success and result.metadata:
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


async def _send_track(message: Message, result: DownloadResult) -> None:
    """Send a single track: cover photo then audio."""
    metadata = result.metadata
    if not metadata:
        return

    caption = _build_track_caption(metadata)
    with contextlib.suppress(Exception):
        if metadata.cover_url:
            await message.reply_photo(metadata.cover_url, caption=caption)
        else:
            await message.reply_text(caption)

    await asyncio.sleep(4)

    await _send_single_audio(message, result)


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
