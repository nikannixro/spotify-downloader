"""Configuration module — loads all settings from environment variables."""

from __future__ import annotations

import os


class _Config:
    # Telegram
    BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
    ADMIN_ID: str = os.environ["ADMIN_ID"]
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
    LOG_FILE: str = os.getenv("LOG_FILE", "bot.log")

    # Cookie file for yt-dlp (YouTube authentication)
    COOKIE_FILE: str = os.getenv("COOKIE_FILE", "")


cfg = _Config()


def is_admin(uid: int) -> bool:
    """Return True if *uid* matches the configured admin ID."""
    return str(uid) == cfg.ADMIN_ID
