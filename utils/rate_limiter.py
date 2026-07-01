"""Rate limiter — per-user download throttling with SQLite persistence."""

from __future__ import annotations

import logging
import time

from services import get_db

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window rate limiter per user ID, backed by SQLite."""

    def __init__(self) -> None:
        pass

    async def _load_limits(self) -> tuple[int, int]:
        """Fetch (max_requests, window_seconds) from database settings."""
        db = get_db()
        try:
            max_requests = int(await db.get_setting("rate_limit_max", "3"))
        except (ValueError, TypeError):
            max_requests = 3
        try:
            window = int(await db.get_setting("rate_limit_window", "60"))
        except (ValueError, TypeError):
            window = 60
        return max_requests, window

    async def is_limited(self, user_id: int) -> bool:
        """Check whether the user has exceeded the rate limit; records a hit if not."""
        db = get_db()
        max_requests, window = await self._load_limits()
        now = time.time()
        hits = await db.get_rate_hits(user_id, window)
        if len(hits) >= max_requests:
            logger.warning(
                "Rate limit hit for user %d (%d/%d in %ds)",
                user_id,
                len(hits),
                max_requests,
                window,
            )
            return True
        await db.record_rate_hit(user_id, now)
        return False

    async def reset(self, user_id: int) -> None:
        """Clear all recorded hits for a user."""
        await get_db().clear_rate_hits(user_id)

    async def remaining(self, user_id: int) -> int:
        """Return how many requests the user can still make in the current window."""
        db = get_db()
        max_requests, window = await self._load_limits()
        hits = await db.get_rate_hits(user_id, window)
        return max(0, max_requests - len(hits))

    async def window_seconds(self) -> int:
        """Return the current rate-limit window in seconds."""
        _, window = await self._load_limits()
        return window
