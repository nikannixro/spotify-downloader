"""State management for admin conversation flow."""

from __future__ import annotations

from typing import Any

from models import AdminState

# Per-user state tracking
_user_states: dict[int, AdminState] = {}
_user_data: dict[int, dict[str, Any]] = {}


def get_state(user_id: int) -> AdminState | None:
    return _user_states.get(user_id)


def set_state(user_id: int, state: AdminState) -> None:
    _user_states[user_id] = state


def clear_state(user_id: int) -> None:
    _user_states.pop(user_id, None)
    _user_data.pop(user_id, None)


def get_user_data(user_id: int) -> dict[str, Any]:
    return _user_data.setdefault(user_id, {})
