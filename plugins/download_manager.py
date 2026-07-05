"""Per-user download task tracker for cancellation support."""

from __future__ import annotations

import asyncio
import logging
import shutil

logger = logging.getLogger(__name__)

_user_tasks: dict[int, set[asyncio.Task]] = {}
_user_cancelled: set[int] = set()
_user_temp_dirs: dict[int, set[str]] = {}
_task_id_counter: int = 0
_task_id_map: dict[int, asyncio.Task] = {}


def _next_task_id() -> int:
    global _task_id_counter
    _task_id_counter += 1
    return _task_id_counter


def register(user_id: int, task: asyncio.Task) -> int:
    """Register an asyncio task for a user. Returns a stable task ID."""
    _user_tasks.setdefault(user_id, set()).add(task)
    task_id = _next_task_id()
    _task_id_map[task_id] = task
    return task_id


def unregister(user_id: int, task: asyncio.Task) -> None:
    """Remove a completed task from the user's active set."""
    tasks = _user_tasks.get(user_id)
    if tasks:
        tasks.discard(task)
        if not tasks:
            _user_tasks.pop(user_id, None)
    # Clean up task ID mapping
    stale_ids = [tid for tid, t in _task_id_map.items() if t is task]
    for tid in stale_ids:
        _task_id_map.pop(tid, None)


def cancel_all(user_id: int) -> int:
    """Cancel all active tasks for a user; return the count of cancelled tasks."""
    tasks = _user_tasks.get(user_id, set()).copy()
    count = 0
    for task in tasks:
        if not task.done():
            task.cancel()
            count += 1
    _user_cancelled.add(user_id)
    return count


def cancel_task(user_id: int, task_id: int) -> bool:
    """Cancel a specific task by its stable ID; return True if a task was cancelled."""
    task = _task_id_map.get(task_id)
    if task and not task.done():
        task.cancel()
        _user_cancelled.add(user_id)
        return True
    return False


def is_cancelled(user_id: int) -> bool:
    """Return True if the user has triggered a cancellation."""
    return user_id in _user_cancelled


def clear_cancel_flag(user_id: int) -> None:
    """Clear the cancellation flag for a user."""
    _user_cancelled.discard(user_id)


def has_active(user_id: int) -> bool:
    """Return True if the user has any running download tasks."""
    tasks = _user_tasks.get(user_id, set())
    return any(not t.done() for t in tasks)


def register_temp_dir(user_id: int, path: str) -> None:
    """Track a temporary directory for cleanup on cancellation."""
    _user_temp_dirs.setdefault(user_id, set()).add(path)


def unregister_temp_dir(user_id: int, path: str) -> None:
    """Stop tracking a temporary directory."""
    dirs = _user_temp_dirs.get(user_id)
    if dirs:
        dirs.discard(path)


def cleanup_user_files(user_id: int) -> None:
    """Remove all temporary directories associated with a user."""
    dirs = _user_temp_dirs.pop(user_id, set())
    for d in dirs:
        try:
            shutil.rmtree(d, ignore_errors=True)
            logger.info("Cleaned up temp dir for user %d: %s", user_id, d)
        except Exception as exc:
            logger.warning("Failed to clean temp dir %s: %s", d, exc)
