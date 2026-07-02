"""Database layer — async SQLite with aiosqlite, indexes, and thread safety."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import Any

import aiosqlite

from config import cfg
from models import ChannelRecord

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite database wrapper using aiosqlite."""

    def __init__(self, db_path: str | None = None) -> None:
        self._path: str = db_path or cfg.DB_PATH
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    async def _init_schema(self) -> None:
        conn = await self._get_conn()
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                join_date  TEXT,
                is_banned  INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned);

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS channels (
                channel_id    TEXT PRIMARY KEY,
                channel_title TEXT,
                invite_link   TEXT
            );

            CREATE TABLE IF NOT EXISTS download_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                track_id   TEXT,
                track_name TEXT,
                log_date   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_dl_user ON download_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_dl_date ON download_log(log_date);

            CREATE TABLE IF NOT EXISTS cache (
                track_id   TEXT PRIMARY KEY,
                file_path  TEXT,
                filename   TEXT,
                created_at TEXT,
                size_bytes INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_cache_created ON cache(created_at);

            CREATE TABLE IF NOT EXISTS rate_limit_hits (
                user_id    INTEGER,
                hit_time   REAL,
                PRIMARY KEY (user_id, hit_time)
            );
            CREATE INDEX IF NOT EXISTS idx_rl_user ON rate_limit_hits(user_id);
        """)
        defaults = [
            (
                "start_message",
                "سلام! اینجا ربات نیکسو اسپاتیفای هست 🗽\n\nاز دکمه های زیر برای سرچ اسم خواننده، آلبوم یا آهنگ استفاده کن 👇",
            ),
            ("download_count", "0"),
            ("maintenance_mode", "0"),
            ("rate_limit_max", "3"),
            ("rate_limit_window", "60"),
            (
                "join_message",
                "سلام خوش اومدی🌹\n✨ برای استفاده از ربات، لطفاً ابتدا در کانال‌ها عضو شوید:",
            ),
        ]
        for key, value in defaults:
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await conn.commit()
        logger.info("Database initialized at %s", self._path)

    async def ensure_initialized(self) -> None:
        await self._init_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def get_path(self) -> str:
        return self._path

    async def get_size_bytes(self) -> int:
        try:
            return os.path.getsize(self._path)
        except OSError:
            return 0

    # ── users ──

    async def add_user(self, user_id: int, username: str | None = None) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)",
            (user_id, username or "unknown", datetime.date.today().isoformat()),
        )
        await conn.commit()

    async def get_users_count(self) -> int:
        admin_id = int(cfg.ADMIN_ID)
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE user_id!=?", (admin_id,))
        row = await cursor.fetchone()
        return row[0]

    async def get_all_user_ids(self) -> list[int]:
        admin_id = int(cfg.ADMIN_ID)
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT user_id FROM users WHERE is_banned=0 AND user_id!=?",
            (admin_id,),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    # ── settings ──

    async def get_setting(self, key: str, default: str = "") -> str:
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await conn.commit()

    # ── downloads ──

    async def log_download(self, user_id: int, track_id: str, track_name: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "INSERT INTO download_log (user_id, track_id, track_name, log_date) "
            "VALUES (?, ?, ?, ?)",
            (user_id, track_id, track_name, datetime.date.today().isoformat()),
        )
        await conn.execute(
            "UPDATE settings SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) "
            "WHERE key = 'download_count'"
        )
        await conn.commit()

    async def get_download_count(self) -> int:
        return int(await self.get_setting("download_count", "0"))

    async def get_today_download_count(self) -> int:
        today = datetime.date.today().isoformat()
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM download_log WHERE log_date=?", (today,))
        row = await cursor.fetchone()
        return row[0]

    async def get_recent_downloads(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = await self._get_conn()
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT user_id, track_name, log_date FROM download_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ── channels ──

    async def add_channel(self, channel_id: str, title: str, link: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO channels VALUES (?, ?, ?)",
            (channel_id, title, link),
        )
        await conn.commit()

    async def get_channels(self) -> list[ChannelRecord]:
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT channel_id, channel_title, invite_link FROM channels")
        rows = await cursor.fetchall()
        return [ChannelRecord(row[0], row[1], row[2]) for row in rows]

    async def remove_channel(self, channel_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM channels WHERE channel_id=?", (channel_id,))
        await conn.commit()

    # ── cache ──

    async def cache_get(self, track_id: str) -> dict[str, Any] | None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT track_id, file_path, filename, created_at, size_bytes "
            "FROM cache WHERE track_id=?",
            (track_id,),
        )
        row = await cursor.fetchone()
        if row:
            return {
                "track_id": row[0],
                "file_path": row[1],
                "filename": row[2],
                "created_at": row[3],
                "size_bytes": row[4],
            }
        return None

    async def cache_put(
        self, track_id: str, file_path: str, filename: str, size_bytes: int = 0
    ) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO cache "
            "(track_id, file_path, filename, created_at, size_bytes) "
            "VALUES (?, ?, ?, ?, ?)",
            (track_id, file_path, filename, datetime.datetime.now().isoformat(), size_bytes),
        )
        await conn.commit()

    async def cache_remove(self, track_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM cache WHERE track_id=?", (track_id,))
        await conn.commit()

    async def cache_get_stats(self) -> dict[str, int]:
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM cache")
        total = (await cursor.fetchone())[0]
        cursor = await conn.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM cache")
        size = (await cursor.fetchone())[0]
        return {"total_files": total, "total_size_bytes": size}

    async def _remove_old_cache_entries(self, cutoff: str) -> int:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT track_id, file_path, size_bytes FROM cache WHERE created_at < ?",
            (cutoff,),
        )
        old_entries = await cursor.fetchall()
        loop = asyncio.get_running_loop()
        for row in old_entries:
            try:
                await loop.run_in_executor(None, self._safe_remove_file, row[1])
            except OSError:
                pass
        await conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
        return len(old_entries)

    @staticmethod
    def _safe_remove_file(path: str) -> None:
        """Remove a file if it exists. Intended for use in a thread executor."""
        if os.path.exists(path):
            os.remove(path)

    async def _trim_cache_to_size(self, max_size_mb: int) -> int:
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM cache")
        total_size: int = (await cursor.fetchone())[0]
        max_bytes = max_size_mb * 1024 * 1024
        if total_size <= max_bytes:
            return 0

        cursor = await conn.execute(
            "SELECT track_id, file_path, size_bytes FROM cache ORDER BY created_at ASC"
        )
        excess = await cursor.fetchall()

        freed = 0
        removed = 0
        loop = asyncio.get_running_loop()
        for row in excess:
            if freed >= (total_size - max_bytes):
                break
            try:
                await loop.run_in_executor(None, self._safe_remove_file, row[1])
            except OSError:
                pass
            freed += row[2]
            await conn.execute("DELETE FROM cache WHERE track_id=?", (row[0],))
            removed += 1
        return removed

    async def cache_cleanup(self, max_age_days: int = 7, max_size_mb: int = 500) -> int:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=max_age_days)).isoformat()
        removed = await self._remove_old_cache_entries(cutoff)
        removed += await self._trim_cache_to_size(max_size_mb)
        await (await self._get_conn()).commit()
        return removed

    # ── rate limit persistence ──

    async def record_rate_hit(self, user_id: int, timestamp: float) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "INSERT INTO rate_limit_hits (user_id, hit_time) VALUES (?, ?)",
            (user_id, timestamp),
        )
        await conn.commit()

    async def get_rate_hits(self, user_id: int, window_seconds: int) -> list[float]:
        import time

        cutoff = time.time() - window_seconds
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT hit_time FROM rate_limit_hits WHERE user_id=? AND hit_time>=? ORDER BY hit_time",
            (user_id, cutoff),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def clear_rate_hits(self, user_id: int) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM rate_limit_hits WHERE user_id=?", (user_id,))
        await conn.commit()

    async def clear_old_rate_hits(self, max_age_seconds: float = 300) -> None:
        import time

        cutoff = time.time() - max_age_seconds
        conn = await self._get_conn()
        await conn.execute("DELETE FROM rate_limit_hits WHERE hit_time<?", (cutoff,))
        await conn.commit()
