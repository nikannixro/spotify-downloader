"""Spotify link parsing, filename sanitization, and uptime formatting utilities."""

from __future__ import annotations

import enum
import logging
import platform
import re
import time
import unicodedata
import urllib.request

logger = logging.getLogger(__name__)

BOT_START_TIME: float = time.time()

SPOTIFY_TRACK_REGEX = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-zA-Z]+/)?track/([a-zA-Z0-9]+)"
)
SPOTIFY_ARTIST_REGEX = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-zA-Z]+/)?artist/([a-zA-Z0-9]+)"
)
SPOTIFY_ALBUM_REGEX = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-zA-Z]+/)?album/([a-zA-Z0-9]+)"
)
SPOTIFY_PLAYLIST_REGEX = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-zA-Z]+/)?playlist/([a-zA-Z0-9]+)"
)
SPOTIFY_URI_REGEX = re.compile(r"spotify:(track|artist|album|playlist):([a-zA-Z0-9]+)")

SAFE_FILENAME_REGEX = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class SpotifyLinkType(enum.Enum):
    """Spotify URL type detected in a message."""

    TRACK = "track"
    ARTIST = "artist"
    ALBUM = "album"
    PLAYLIST = "playlist"


_URI_TYPE_MAP: dict[str, SpotifyLinkType] = {
    "track": SpotifyLinkType.TRACK,
    "artist": SpotifyLinkType.ARTIST,
    "album": SpotifyLinkType.ALBUM,
    "playlist": SpotifyLinkType.PLAYLIST,
}


def parse_spotify_link(text: str) -> tuple[SpotifyLinkType, str] | None:
    """Return (type, id) for the first Spotify URL found in *text*, or None."""
    for link_type, regex in [
        (SpotifyLinkType.TRACK, SPOTIFY_TRACK_REGEX),
        (SpotifyLinkType.ARTIST, SPOTIFY_ARTIST_REGEX),
        (SpotifyLinkType.ALBUM, SPOTIFY_ALBUM_REGEX),
        (SpotifyLinkType.PLAYLIST, SPOTIFY_PLAYLIST_REGEX),
    ]:
        match = regex.search(text)
        if match:
            return link_type, match.group(1)

    uri_match = SPOTIFY_URI_REGEX.search(text)
    if uri_match:
        type_str, resource_id = uri_match.group(1), uri_match.group(2)
        link_type = _URI_TYPE_MAP.get(type_str)
        if link_type:
            return link_type, resource_id

    return None


def extract_track_id(text: str) -> str | None:
    """Extract the track ID from a Spotify track URL, or None."""
    match = SPOTIFY_TRACK_REGEX.search(text)
    return match.group(1) if match else None


async def download_cover_bytes(url: str) -> bytes | None:
    """Download cover art and return raw bytes, or None on failure."""
    import asyncio

    def _fetch() -> bytes | None:
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                return response.read()
        except Exception as exc:
            logger.warning("Failed to download cover from %s: %s", url, exc)
            return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch)


def sanitize_filename(name: str) -> str:
    """Strip characters unsafe for file systems and truncate to 200 chars."""
    name = unicodedata.normalize("NFC", name)
    name = SAFE_FILENAME_REGEX.sub("_", name)
    name = name.strip(". ")
    return name[:200] if name else "untitled"


def sanitize_slug(text: str) -> str:
    """Convert text to a Telegram-safe slug: lowercase alphanumeric + single underscores."""
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    text = re.sub(r'\s+', '_', text.strip())
    return text.lower()


def _format_uptime(seconds: int) -> str:
    """Format seconds into a human-readable 'Nd Nh Nm Ns' string."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def uptime_string() -> str:
    """Return human-readable bot uptime (e.g. '2h 15m 30s')."""
    seconds = int(time.time() - BOT_START_TIME)
    return _format_uptime(seconds)


def server_uptime_string() -> str:
    """Return human-readable server uptime, or Persian 'نامشخص' on failure."""
    try:
        if platform.system() == "Linux":
            with open("/proc/uptime") as f:
                uptime_seconds = float(f.readline().split()[0])
        else:
            import psutil

            uptime_seconds = time.time() - psutil.boot_time()
    except Exception:
        return "نامشخص"

    return _format_uptime(int(uptime_seconds))


def bytes_to_human(size_bytes: int) -> str:
    """Convert a byte count to a human-readable string like '1.50 MB'."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"
