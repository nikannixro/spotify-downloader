"""Standalone yt-dlp download module — bypasses spotDL for audio download."""

from __future__ import annotations

import logging
import os

from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)

_YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "audioformat": "best",
    "default_search": "ytsearch",
    "noplaylist": True,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "quiet": True,
    "no_warnings": True,
    "encoding": "UTF-8",
}


def download_track(
    query: str,
    output_dir: str,
    cookie_file: str | None = None,
) -> str | None:
    """Search YouTube and download audio as FLAC.

    Args:
        query: Search query (e.g. "Artist - Title").
        output_dir: Directory to save the downloaded file.
        cookie_file: Optional path to Netscape cookies.txt for YouTube auth.

    Returns:
        Path to the downloaded .flac file, or None on failure.
    """
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    opts = {
        **_YTDL_OPTIONS,
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "flac",
                "preferredquality": "0",
            }
        ],
    }

    if cookie_file and os.path.isfile(cookie_file):
        opts["cookiefile"] = cookie_file

    attempts = [query, f"{query} lyrics"]

    for attempt_query in attempts:
        try:
            result = _try_download(opts, attempt_query)
            if result:
                return result
        except Exception as exc:
            logger.warning("yt-dlp attempt failed for '%s': %s", attempt_query, exc)

    logger.error("All yt-dlp attempts failed for query: %s", query)
    return None


def _try_download(opts: dict, query: str) -> str | None:
    """Execute a single download attempt: search then download.

    Returns the path to the downloaded .flac file, or None.
    """
    with YoutubeDL(opts) as ydl:
        logger.info("Searching YouTube: %s", query)
        info = ydl.extract_info(f"ytsearch:{query}", download=False)

        if not info or "entries" not in info or not info["entries"]:
            logger.warning("No YouTube results for: %s", query)
            return None

        entry = info["entries"][0]
        if not entry or not entry.get("id"):
            logger.warning("Invalid YouTube result for: %s", query)
            return None

        video_id = entry["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("Downloading: %s", video_url)

        ydl.download([video_url])

        filename = ydl.prepare_filename(entry)
        flac_path = os.path.splitext(filename)[0] + ".flac"

        if os.path.isfile(flac_path):
            logger.info("Downloaded: %s", os.path.basename(flac_path))
            return flac_path

        logger.warning("Expected file not found: %s", flac_path)
        return None
