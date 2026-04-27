"""Tests for Streamlit admin session-state helpers."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from admin.state.session import (  # noqa: E402
    bootstrap_admin_session_state,
    clear_admin_session,
    get_admin_access_token,
    get_admin_auth_error,
    get_admin_profile,
    is_admin_authenticated,
    set_admin_auth_error,
    set_admin_session,
)


def test_admin_session_state_helpers_round_trip() -> None:
    """Session helpers should persist and clear admin auth state predictably."""
    state: dict[str, object] = {}

    bootstrap_admin_session_state(state)
    assert is_admin_authenticated(state) is False
    assert get_admin_access_token(state) is None
    assert get_admin_profile(state) is None
    assert get_admin_auth_error(state) is None

    set_admin_auth_error(state, "登录失败")
    assert get_admin_auth_error(state) == "登录失败"

    set_admin_session(
        state,
        access_token="jwt-token",
        admin_profile={"id": 1, "username": "platform.admin"},
    )
    assert is_admin_authenticated(state) is True
    assert get_admin_access_token(state) == "jwt-token"
    assert get_admin_profile(state) == {"id": 1, "username": "platform.admin"}
    assert get_admin_auth_error(state) is None

    clear_admin_session(state)
    assert is_admin_authenticated(state) is False
    assert get_admin_access_token(state) is None
    assert get_admin_profile(state) is None
