"""Bot entry point — wires all handlers and starts polling via Pyrogram."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# Pyrogram 2.x calls asyncio.get_event_loop() at import time.
# Python 3.12+ no longer creates a default loop, so we must set one first.
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "config.env"))

import structlog  # noqa: E402
from pyrogram import Client, enums  # noqa: E402
from pyrogram.methods.utilities.idle import idle  # noqa: E402

import plugins.download_manager as download_manager  # noqa: E402
from config import cfg  # noqa: E402
from services import close_all, get_cache, get_db  # noqa: E402
from utils.log_channel_handler import get_log_channel_handler  # noqa: E402

_NOISY_LOGGERS: list[str] = [
    "httpx",
    "httpcore",
    "spotipy",
    "urllib3",
    "pyrogram",
]

REQUIRED_ENV_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "ADMIN_ID",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
]

log = structlog.get_logger()

_log_channel_handler = get_log_channel_handler()


class _LazyFileHandler(logging.FileHandler):
    def _open(self) -> object:
        log_path = self.baseFilename
        log_dir = os.path.dirname(log_path)

        if not log_dir:
            log_dir = "logs"
            new_path = os.path.join(log_dir, os.path.basename(log_path))
            self.baseFilename = os.path.abspath(new_path)

        os.makedirs(log_dir, exist_ok=True)
        return super()._open()


def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, cfg.LOG_LEVEL.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _log_channel_handler.setLevel(logging.DEBUG)
    _log_channel_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            _LazyFileHandler(cfg.LOG_FILE, encoding="utf-8"),
            _log_channel_handler,
        ],
    )
    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def validate_environment() -> None:
    """Validate all required environment variables and configuration."""
    missing = [k for k in REQUIRED_ENV_VARS if not os.getenv(k)]
    if missing:
        for key in missing:
            log.error("missing.env_var", key=key)
        sys.exit(1)

    token = cfg.BOT_TOKEN
    if ":" not in token or len(token.split(":")) != 2:
        log.error("invalid.token_format")
        sys.exit(1)
    token_parts = token.split(":")
    if not token_parts[0].isdigit():
        log.error("invalid.token_bot_id")
        sys.exit(1)

    try:
        int(cfg.ADMIN_ID)
    except (ValueError, TypeError):
        log.error("invalid.admin_id", value=cfg.ADMIN_ID)
        sys.exit(1)

    db_dir = os.path.dirname(cfg.DB_PATH)
    if db_dir and not os.access(db_dir, os.W_OK):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError:
            log.error("db_path_not_writable", path=cfg.DB_PATH)
            sys.exit(1)

    log.info("environment.validated")


def preflight_checks() -> bool:
    """Check that required Python packages are available."""
    try:
        import spotdl  # noqa: F401
    except ImportError:
        log.error("spotdl.not_installed")
        return False
    return True


async def on_startup(app: Client) -> None:
    """Called after Pyrogram client starts — initialize DB, load handlers, cleanup."""
    _log_channel_handler.set_client(app)

    # Cache bot username for deep links
    me = await app.get_me()
    cfg.BOT_USERNAME = me.username
    log.info("bot.username", username=me.username)

    db = get_db()
    await db.ensure_initialized()
    log.info("database.ready", path=db.get_path())

    # Load persisted log-channel settings into the handler so logs flow to the
    # configured Telegram channel immediately after startup (without requiring
    # an admin to re-configure it via the panel).
    await _log_channel_handler.reload()

    cache = get_cache()
    removed = await cache.cleanup()
    if removed:
        log.info("cache.cleanup", removed=removed)

    expired = await db.clear_old_rate_hits(max_age_seconds=300)
    if expired:
        log.info("rate_limit.cleanup", expired=expired)

    # Import handler modules — decorators attach .handlers to functions
    from pyrogram.handlers.handler import Handler
    from handlers import start, download, inline, callbacks, states
    from handlers.admin import panel, broadcast, channels, settings, log_channel

    # Register handlers with the Client instance
    modules = [start, download, inline, callbacks, states, panel, broadcast, channels, settings, log_channel]
    count = 0
    for module in modules:
        for name in vars(module):
            obj = getattr(module, name)
            if hasattr(obj, 'handlers') and isinstance(obj.handlers, list):
                for handler, group in obj.handlers:
                    if isinstance(handler, Handler) and isinstance(group, int):
                        app.add_handler(handler, group)
                        count += 1
    log.info("handlers.loaded", count=count)

    log.info("bot.started")


async def shutdown(app: Client) -> None:
    """Graceful shutdown — wait for active downloads to finish."""
    log.info("shutdown.started")
    active_users = [
        uid for uid in list(download_manager._user_tasks.keys()) if download_manager.has_active(uid)
    ]
    if active_users:
        log.info("shutdown.waiting_for_downloads", active_count=len(active_users))
        try:
            await asyncio.wait_for(_drain_active_downloads(), timeout=30)
        except asyncio.TimeoutError:
            log.warning("shutdown.timeout_forced")

    await close_all()

    log.info("shutdown.complete")


async def _drain_active_downloads():
    """Wait until no active downloads remain."""
    while True:
        has_any = False
        for uid in list(download_manager._user_tasks.keys()):
            if download_manager.has_active(uid):
                has_any = True
                break
        if not has_any:
            break
        await asyncio.sleep(0.5)


def main() -> None:
    setup_logging()
    validate_environment()

    if not preflight_checks():
        sys.exit(1)

    # Increase default timeout for file uploads (default 15s too low)
    import pyrogram.session.session as _sess
    _sess.Session.invoke.__defaults__ = (10, 20, 10)

    # Create Pyrogram client — handlers loaded manually in on_startup
    app = Client(
        "spotify_bot",
        api_id=cfg.API_ID,
        api_hash=cfg.API_HASH,
        bot_token=cfg.BOT_TOKEN,
        workdir=".",
        parse_mode=enums.ParseMode.MARKDOWN,
    )

    async def _run():
        async with app:
            await on_startup(app)
            try:
                await idle()
            finally:
                await shutdown(app)

    log.info("bot.initializing")

    # Run with Pyrogram (blocks until the client is stopped)
    try:
        app.run(_run())
    except KeyboardInterrupt:
        log.info("bot.stopped")


if __name__ == "__main__":
    main()
