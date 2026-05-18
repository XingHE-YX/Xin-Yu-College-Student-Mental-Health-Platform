"""Session-state helpers for the Streamlit admin console."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

SESSION_KEY_ACCESS_TOKEN = "admin_access_token"
SESSION_KEY_PROFILE = "admin_profile"
SESSION_KEY_AUTH_ERROR = "admin_auth_error"
SESSION_KEY_ACTIVE_VIEW = "admin_active_view"
SESSION_KEY_SELECTED_ALERT_ID = "admin_selected_alert_id"
SESSION_KEY_SELECTED_ALERT_DETAIL = "admin_selected_alert_detail"
SESSION_KEY_ALERT_FEEDBACK = "admin_alert_feedback"
SESSION_KEY_SELECTED_POST_ID = "admin_selected_post_id"
SESSION_KEY_SELECTED_POST_DETAIL = "admin_selected_post_detail"
SESSION_KEY_SELECTED_USER_ID = "admin_selected_user_id"
SESSION_KEY_SELECTED_USER_DETAIL = "admin_selected_user_detail"


def bootstrap_admin_session_state(state: MutableMapping[str, Any]) -> None:
    """Ensure the admin session keys always exist."""
    state.setdefault(SESSION_KEY_ACCESS_TOKEN, None)
    state.setdefault(SESSION_KEY_PROFILE, None)
    state.setdefault(SESSION_KEY_AUTH_ERROR, None)
    state.setdefault(SESSION_KEY_ACTIVE_VIEW, "dashboard")
    state.setdefault(SESSION_KEY_SELECTED_ALERT_ID, None)
    state.setdefault(SESSION_KEY_SELECTED_ALERT_DETAIL, None)
    state.setdefault(SESSION_KEY_ALERT_FEEDBACK, None)
    state.setdefault(SESSION_KEY_SELECTED_POST_ID, None)
    state.setdefault(SESSION_KEY_SELECTED_POST_DETAIL, None)
    state.setdefault(SESSION_KEY_SELECTED_USER_ID, None)
    state.setdefault(SESSION_KEY_SELECTED_USER_DETAIL, None)


def set_admin_session(
    state: MutableMapping[str, Any],
    *,
    access_token: str,
    admin_profile: dict[str, Any],
    reset_workspace: bool = True,
) -> None:
    """Persist a successful admin session inside Streamlit session state."""
    state[SESSION_KEY_ACCESS_TOKEN] = access_token
    state[SESSION_KEY_PROFILE] = admin_profile
    state[SESSION_KEY_AUTH_ERROR] = None
    if not reset_workspace:
        return
    state[SESSION_KEY_ACTIVE_VIEW] = "dashboard"
    state[SESSION_KEY_SELECTED_ALERT_ID] = None
    state[SESSION_KEY_SELECTED_ALERT_DETAIL] = None
    state[SESSION_KEY_ALERT_FEEDBACK] = None
    state[SESSION_KEY_SELECTED_POST_ID] = None
    state[SESSION_KEY_SELECTED_POST_DETAIL] = None
    state[SESSION_KEY_SELECTED_USER_ID] = None
    state[SESSION_KEY_SELECTED_USER_DETAIL] = None


def clear_admin_session(state: MutableMapping[str, Any]) -> None:
    """Clear all admin-authenticated session state."""
    state[SESSION_KEY_ACCESS_TOKEN] = None
    state[SESSION_KEY_PROFILE] = None
    state[SESSION_KEY_ACTIVE_VIEW] = "dashboard"
    state[SESSION_KEY_SELECTED_ALERT_ID] = None
    state[SESSION_KEY_SELECTED_ALERT_DETAIL] = None
    state[SESSION_KEY_ALERT_FEEDBACK] = None
    state[SESSION_KEY_SELECTED_POST_ID] = None
    state[SESSION_KEY_SELECTED_POST_DETAIL] = None
    state[SESSION_KEY_SELECTED_USER_ID] = None
    state[SESSION_KEY_SELECTED_USER_DETAIL] = None


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


def set_admin_active_view(state: MutableMapping[str, Any], view_name: str) -> None:
    """Persist the current top-level admin workspace view."""
    state[SESSION_KEY_ACTIVE_VIEW] = view_name


def get_admin_active_view(state: MutableMapping[str, Any]) -> str:
    """Return the current top-level admin workspace view."""
    value = state.get(SESSION_KEY_ACTIVE_VIEW)
    return value if isinstance(value, str) and value else "dashboard"


def set_selected_alert_detail(
    state: MutableMapping[str, Any],
    *,
    alert_id: int,
    alert_detail: dict[str, Any],
) -> None:
    """Persist the currently selected alert detail payload."""
    state[SESSION_KEY_SELECTED_ALERT_ID] = alert_id
    state[SESSION_KEY_SELECTED_ALERT_DETAIL] = alert_detail


def get_selected_alert_id(state: MutableMapping[str, Any]) -> int | None:
    """Return the currently selected alert id, if any."""
    value = state.get(SESSION_KEY_SELECTED_ALERT_ID)
    return value if isinstance(value, int) else None


def get_selected_alert_detail(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    """Return the cached selected alert detail payload."""
    value = state.get(SESSION_KEY_SELECTED_ALERT_DETAIL)
    return value if isinstance(value, dict) else None


def clear_selected_alert_detail(state: MutableMapping[str, Any]) -> None:
    """Clear the current alert-detail selection cache."""
    state[SESSION_KEY_SELECTED_ALERT_ID] = None
    state[SESSION_KEY_SELECTED_ALERT_DETAIL] = None


def set_admin_alert_feedback(
    state: MutableMapping[str, Any],
    feedback: dict[str, str] | None,
) -> None:
    """Store one transient admin workspace feedback message."""
    state[SESSION_KEY_ALERT_FEEDBACK] = feedback


def pop_admin_alert_feedback(
    state: MutableMapping[str, Any],
) -> dict[str, str] | None:
    """Return and clear one transient admin workspace feedback message."""
    value = state.get(SESSION_KEY_ALERT_FEEDBACK)
    state[SESSION_KEY_ALERT_FEEDBACK] = None
    return value if isinstance(value, dict) else None


def set_selected_post_detail(
    state: MutableMapping[str, Any],
    *,
    post_id: int,
    post_detail: dict[str, Any],
) -> None:
    """Persist the currently selected admin post detail payload."""
    state[SESSION_KEY_SELECTED_POST_ID] = post_id
    state[SESSION_KEY_SELECTED_POST_DETAIL] = post_detail


def get_selected_post_id(state: MutableMapping[str, Any]) -> int | None:
    """Return the currently selected admin post id, if any."""
    value = state.get(SESSION_KEY_SELECTED_POST_ID)
    return value if isinstance(value, int) else None


def get_selected_post_detail(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    """Return the cached selected admin post detail payload."""
    value = state.get(SESSION_KEY_SELECTED_POST_DETAIL)
    return value if isinstance(value, dict) else None


def clear_selected_post_detail(state: MutableMapping[str, Any]) -> None:
    """Clear the current admin post detail selection cache."""
    state[SESSION_KEY_SELECTED_POST_ID] = None
    state[SESSION_KEY_SELECTED_POST_DETAIL] = None


def set_selected_user_detail(
    state: MutableMapping[str, Any],
    *,
    student_id: int,
    user_detail: dict[str, Any],
) -> None:
    """Persist the currently selected admin user detail payload."""
    state[SESSION_KEY_SELECTED_USER_ID] = student_id
    state[SESSION_KEY_SELECTED_USER_DETAIL] = user_detail


def get_selected_user_id(state: MutableMapping[str, Any]) -> int | None:
    """Return the currently selected admin user id, if any."""
    value = state.get(SESSION_KEY_SELECTED_USER_ID)
    return value if isinstance(value, int) else None


def get_selected_user_detail(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    """Return the cached selected admin user detail payload."""
    value = state.get(SESSION_KEY_SELECTED_USER_DETAIL)
    return value if isinstance(value, dict) else None


def clear_selected_user_detail(state: MutableMapping[str, Any]) -> None:
    """Clear the current admin user detail selection cache."""
    state[SESSION_KEY_SELECTED_USER_ID] = None
    state[SESSION_KEY_SELECTED_USER_DETAIL] = None
