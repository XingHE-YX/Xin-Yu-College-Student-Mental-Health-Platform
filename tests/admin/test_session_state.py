"""Tests for Streamlit admin session-state helpers."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from admin.state.session import (  # noqa: E402
    bootstrap_admin_session_state,
    clear_selected_alert_detail,
    clear_selected_post_detail,
    clear_selected_user_detail,
    clear_admin_session,
    get_admin_active_view,
    get_admin_access_token,
    get_admin_auth_error,
    get_admin_profile,
    get_selected_alert_detail,
    get_selected_alert_id,
    get_selected_post_detail,
    get_selected_post_id,
    get_selected_user_detail,
    get_selected_user_id,
    is_admin_authenticated,
    pop_admin_alert_feedback,
    set_admin_active_view,
    set_admin_alert_feedback,
    set_admin_auth_error,
    set_admin_session,
    set_selected_alert_detail,
    set_selected_post_detail,
    set_selected_user_detail,
)


def test_admin_session_state_helpers_round_trip() -> None:
    """Session helpers should persist and clear admin auth state predictably."""
    state: dict[str, object] = {}

    bootstrap_admin_session_state(state)
    assert is_admin_authenticated(state) is False
    assert get_admin_access_token(state) is None
    assert get_admin_profile(state) is None
    assert get_admin_auth_error(state) is None
    assert get_admin_active_view(state) == "dashboard"
    assert get_selected_alert_id(state) is None
    assert get_selected_alert_detail(state) is None
    assert get_selected_post_id(state) is None
    assert get_selected_post_detail(state) is None
    assert get_selected_user_id(state) is None
    assert get_selected_user_detail(state) is None
    assert pop_admin_alert_feedback(state) is None

    set_admin_auth_error(state, "登录失败")
    assert get_admin_auth_error(state) == "登录失败"

    set_admin_active_view(state, "alerts")
    assert get_admin_active_view(state) == "alerts"

    set_selected_alert_detail(
        state,
        alert_id=12,
        alert_detail={"alert_id": 12, "queue_status": "pending_review"},
    )
    assert get_selected_alert_id(state) == 12
    assert get_selected_alert_detail(state) == {
        "alert_id": 12,
        "queue_status": "pending_review",
    }

    set_selected_post_detail(
        state,
        post_id=18,
        post_detail={"post_id": 18, "publish_status": "published"},
    )
    assert get_selected_post_id(state) == 18
    assert get_selected_post_detail(state) == {
        "post_id": 18,
        "publish_status": "published",
    }

    set_selected_user_detail(
        state,
        student_id=22,
        user_detail={"student_id": 22, "risk_status": "watch"},
    )
    assert get_selected_user_id(state) == 22
    assert get_selected_user_detail(state) == {
        "student_id": 22,
        "risk_status": "watch",
    }

    set_admin_alert_feedback(state, {"level": "success", "message": "已刷新"})
    assert pop_admin_alert_feedback(state) == {
        "level": "success",
        "message": "已刷新",
    }
    assert pop_admin_alert_feedback(state) is None

    set_admin_session(
        state,
        access_token="jwt-token",
        admin_profile={"id": 1, "username": "platform.admin"},
    )
    assert is_admin_authenticated(state) is True
    assert get_admin_access_token(state) == "jwt-token"
    assert get_admin_profile(state) == {"id": 1, "username": "platform.admin"}
    assert get_admin_auth_error(state) is None
    assert get_admin_active_view(state) == "dashboard"
    assert get_selected_alert_id(state) is None
    assert get_selected_alert_detail(state) is None
    assert get_selected_post_id(state) is None
    assert get_selected_post_detail(state) is None
    assert get_selected_user_id(state) is None
    assert get_selected_user_detail(state) is None


def test_set_admin_session_can_preserve_workspace_when_refreshing_existing_login() -> None:
    """Session refresh should keep the current workspace and detail selections intact."""
    state: dict[str, object] = {}

    bootstrap_admin_session_state(state)
    set_admin_active_view(state, "alerts")
    set_selected_alert_detail(
        state,
        alert_id=9,
        alert_detail={"alert_id": 9, "queue_status": "pending_review"},
    )
    set_admin_alert_feedback(state, {"level": "info", "message": "保留当前工作区"})

    set_admin_session(
        state,
        access_token="refreshed-token",
        admin_profile={"id": 1, "username": "platform.admin", "display_name": "平台管理员"},
        reset_workspace=False,
    )

    assert is_admin_authenticated(state) is True
    assert get_admin_access_token(state) == "refreshed-token"
    assert get_admin_profile(state) == {
        "id": 1,
        "username": "platform.admin",
        "display_name": "平台管理员",
    }
    assert get_admin_active_view(state) == "alerts"
    assert get_selected_alert_id(state) == 9
    assert get_selected_alert_detail(state) == {
        "alert_id": 9,
        "queue_status": "pending_review",
    }
    assert pop_admin_alert_feedback(state) == {
        "level": "info",
        "message": "保留当前工作区",
    }

    set_selected_alert_detail(
        state,
        alert_id=24,
        alert_detail={"alert_id": 24},
    )
    clear_selected_alert_detail(state)
    assert get_selected_alert_id(state) is None
    assert get_selected_alert_detail(state) is None

    set_selected_post_detail(
        state,
        post_id=35,
        post_detail={"post_id": 35},
    )
    clear_selected_post_detail(state)
    assert get_selected_post_id(state) is None
    assert get_selected_post_detail(state) is None

    set_selected_user_detail(
        state,
        student_id=41,
        user_detail={"student_id": 41},
    )
    clear_selected_user_detail(state)
    assert get_selected_user_id(state) is None
    assert get_selected_user_detail(state) is None

    clear_admin_session(state)
    assert is_admin_authenticated(state) is False
    assert get_admin_access_token(state) is None
    assert get_admin_profile(state) is None
    assert get_admin_active_view(state) == "dashboard"
    assert get_selected_alert_id(state) is None
    assert get_selected_alert_detail(state) is None
    assert get_selected_post_id(state) is None
    assert get_selected_post_detail(state) is None
    assert get_selected_user_id(state) is None
    assert get_selected_user_detail(state) is None
