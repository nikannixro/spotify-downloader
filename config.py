"""Configuration module — loads all settings from environment variables."""

from __future__ import annotations

import os


class _Config:
    # Telegram
    BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
    ADMIN_ID: str = os.environ["ADMIN_ID"]
    ADMIN_IDS: str = os.getenv("ADMIN_IDS", "")
    API_ID: str = os.environ["TELEGRAM_API_ID"]
    API_HASH: str = os.environ["TELEGRAM_API_HASH"]

    # Spotify API
    SPOTIFY_CLIENT_ID: str = os.environ["SPOTIFY_CLIENT_ID"]
    SPOTIFY_CLIENT_SECRET: str = os.environ["SPOTIFY_CLIENT_SECRET"]

    # Database
    DB_PATH: str = os.getenv("DB_FILE", "data/database.db")

    # Concurrency / timeouts
    MAX_CONCURRENT: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 3))
    TIMEOUT: int = int(os.getenv("DOWNLOAD_TIMEOUT", 300))

    # Cache
    CACHE_MAX_MB: int = int(os.getenv("CACHE_MAX_SIZE_MB", 500))
    CACHE_MAX_DAYS: int = int(os.getenv("CACHE_MAX_AGE_DAYS", 7))

    # Rate limiting
    RATE_MAX: int = int(os.getenv("RATE_LIMIT_MAX", 3))
    RATE_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", 60))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/bot.log")

    # Cookie file for yt-dlp (YouTube authentication)
    COOKIE_FILE: str = os.getenv("COOKIE_FILE", "cookies.txt")

    # Bot username (populated at startup via client.get_me())
    BOT_USERNAME: str = ""


cfg = _Config()

_admin_ids_cache: set[str] | None = None


def _get_admin_ids() -> set[str]:
    """Return the full set of configured admin IDs (strings). Cached after first call."""
    global _admin_ids_cache
    if _admin_ids_cache is None:
        if cfg.ADMIN_IDS:
            _admin_ids_cache = {s.strip() for s in cfg.ADMIN_IDS.split(",") if s.strip()}
        else:
            _admin_ids_cache = {cfg.ADMIN_ID.strip()} if cfg.ADMIN_ID.strip() else set()
    return _admin_ids_cache


def is_admin(uid: int) -> bool:
    """Return True if *uid* matches any configured admin ID."""
    return str(uid) in _get_admin_ids()


def get_admin_ids() -> list[int]:
    """Return all configured admin IDs as integers."""
    return [int(x) for x in _get_admin_ids() if x.isdigit()]
