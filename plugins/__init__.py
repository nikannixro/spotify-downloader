"""Plugin modules: spotDL backend, cache, and task management."""

from plugins.cache import DownloadCache
from plugins.download_manager import (
    cancel_all,
    cleanup_user_files,
    clear_cancel_flag,
    has_active,
    is_cancelled,
    register,
    register_temp_dir,
    unregister,
    unregister_temp_dir,
)
from plugins.spotdl import SpotDLBackend

__all__ = [
    "DownloadCache",
    "SpotDLBackend",
    "cancel_all",
    "cleanup_user_files",
    "clear_cancel_flag",
    "has_active",
    "is_cancelled",
    "register",
    "register_temp_dir",
    "unregister",
    "unregister_temp_dir",
]
