"""Session-state helpers for the Streamlit admin console."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

SESSION_KEY_ACCESS_TOKEN = "admin_access_token"
SESSION_KEY_PROFILE = "admin_profile"
SESSION_KEY_AUTH_ERROR = "admin_auth_error"


def bootstrap_admin_session_state(state: MutableMapping[str, Any]) -> None:
    """Ensure the admin session keys always exist."""
    state.setdefault(SESSION_KEY_ACCESS_TOKEN, None)
    state.setdefault(SESSION_KEY_PROFILE, None)
    state.setdefault(SESSION_KEY_AUTH_ERROR, None)


def set_admin_session(
    state: MutableMapping[str, Any],
    *,
    access_token: str,
    admin_profile: dict[str, Any],
) -> None:
    """Persist a successful admin session inside Streamlit session state."""
    state[SESSION_KEY_ACCESS_TOKEN] = access_token
    state[SESSION_KEY_PROFILE] = admin_profile
    state[SESSION_KEY_AUTH_ERROR] = None


def clear_admin_session(state: MutableMapping[str, Any]) -> None:
    """Clear all admin-authenticated session state."""
    state[SESSION_KEY_ACCESS_TOKEN] = None
    state[SESSION_KEY_PROFILE] = None


def set_admin_auth_error(state: MutableMapping[str, Any], message: str | None) -> None:
    """Store one login or token-validation error for later display."""
    state[SESSION_KEY_AUTH_ERROR] = message


def get_admin_access_token(state: MutableMapping[str, Any]) -> str | None:
    """Return the current admin access token from session state."""
    value = state.get(SESSION_KEY_ACCESS_TOKEN)
    return value if isinstance(value, str) and value else None


def get_admin_profile(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    """Return the cached admin profile from session state."""
    value = state.get(SESSION_KEY_PROFILE)
    return value if isinstance(value, dict) else None


def get_admin_auth_error(state: MutableMapping[str, Any]) -> str | None:
    """Return the current admin auth error if one exists."""
    value = state.get(SESSION_KEY_AUTH_ERROR)
    return value if isinstance(value, str) and value else None


def is_admin_authenticated(state: MutableMapping[str, Any]) -> bool:
    """Return whether the current Streamlit session carries an admin token."""
    return get_admin_access_token(state) is not None
