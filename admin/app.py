"""Streamlit admin console entrypoint."""

from __future__ import annotations

from typing import Any

import streamlit as st

from admin.services.auth import (
    AdminApiClient,
    AdminApiClientError,
    AdminApiRequestError,
)
from admin.state.session import (
    bootstrap_admin_session_state,
    clear_admin_session,
    get_admin_access_token,
    get_admin_auth_error,
    get_admin_profile,
    is_admin_authenticated,
    set_admin_auth_error,
    set_admin_session,
)
from admin.utils.config import get_admin_api_base_url
from admin.utils.styles import build_admin_console_css


def main() -> None:
    """Render the administrator login flow and session-aware placeholder shell."""
    st.set_page_config(
        page_title="心语管理后台",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(build_admin_console_css(), unsafe_allow_html=True)
    bootstrap_admin_session_state(st.session_state)

    api_client = AdminApiClient(api_base_url=get_admin_api_base_url())
    validate_existing_session(api_client)

    if not is_admin_authenticated(st.session_state):
        render_login_page(api_client)
        return

    render_dashboard_shell()


def validate_existing_session(api_client: AdminApiClient) -> None:
    """Validate any existing admin token stored in session state."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return

    try:
        admin_profile = api_client.get_current_admin(access_token=access_token)
    except AdminApiRequestError as exc:
        clear_admin_session(st.session_state)
        if exc.code == "ADMIN_ACCOUNT_INACTIVE":
            set_admin_auth_error(st.session_state, "当前账户已被禁用，暂时无法访问后台。")
        else:
            set_admin_auth_error(st.session_state, "管理员会话已失效，请重新登录。")
    except AdminApiClientError:
        # Keep the existing token and cached profile when the backend is temporarily
        # unreachable so the Streamlit session does not silently discard state.
        if get_admin_profile(st.session_state) is None:
            clear_admin_session(st.session_state)
            set_admin_auth_error(st.session_state, "暂时无法验证后台会话，请稍后重试。")
        return
    else:
        set_admin_session(
            st.session_state,
            access_token=access_token,
            admin_profile=admin_profile,
        )


def render_login_page(api_client: AdminApiClient) -> None:
    """Render the A01 administrator login page."""
    auth_error = get_admin_auth_error(st.session_state)

    st.markdown('<div class="xinyu-auth-shell">', unsafe_allow_html=True)
    st.markdown('<div class="xinyu-auth-card">', unsafe_allow_html=True)
    st.markdown('<span class="xinyu-auth-eyebrow">A01 Admin Login</span>', unsafe_allow_html=True)
    st.markdown('<h1 class="xinyu-auth-title">心语管理后台</h1>', unsafe_allow_html=True)
    st.markdown(
        (
            '<p class="xinyu-auth-copy">'
            "请输入管理员账号与密码。登录成功后将获取 JWT 会话，并进入总览页。"
            "</p>"
        ),
        unsafe_allow_html=True,
    )

    if auth_error:
        st.error(auth_error)
        set_admin_auth_error(st.session_state, None)

    with st.form("admin-login-form", clear_on_submit=False):
        username = st.text_input("用户名", placeholder="platform.admin")
        password = st.text_input("密码", type="password", placeholder="请输入管理员密码")
        submitted = st.form_submit_button("登录后台", use_container_width=True)

    if submitted:
        handle_login_submit(
            api_client,
            username=username,
            password=password,
        )

    st.markdown(
        (
            '<div class="xinyu-hint-card">'
            f"当前后台 API：<code>{get_admin_api_base_url()}</code><br/>"
            "若数据库中尚未写入管理员账户，登录会返回用户名或密码错误。"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown("</div></div>", unsafe_allow_html=True)


def handle_login_submit(
    api_client: AdminApiClient,
    *,
    username: str,
    password: str,
) -> None:
    """Submit one admin login form and persist the returned JWT in session state."""
    try:
        session_payload = api_client.login(username=username, password=password)
    except AdminApiRequestError as exc:
        if exc.code == "ADMIN_AUTH_INVALID_CREDENTIALS":
            set_admin_auth_error(st.session_state, "用户名或密码错误，请重新输入。")
        elif exc.code == "ADMIN_ACCOUNT_INACTIVE":
            set_admin_auth_error(st.session_state, "当前账户已被禁用，暂时无法访问后台。")
        else:
            set_admin_auth_error(st.session_state, exc.message)
    except AdminApiClientError as exc:
        set_admin_auth_error(st.session_state, str(exc))
    else:
        set_admin_session(
            st.session_state,
            access_token=session_payload.access_token,
            admin_profile=session_payload.admin,
        )
    st.rerun()


def render_dashboard_shell() -> None:
    """Render the authenticated A02 placeholder shell until 11.2 lands."""
    admin_profile = get_admin_profile(st.session_state) or {}
    display_name = str(admin_profile.get("display_name") or "管理员")
    role_code = str(admin_profile.get("role_code") or "platform_admin")

    left, right = st.columns([0.82, 0.18], vertical_alignment="center")
    with left:
        st.markdown(
            (
                '<div class="xinyu-topbar">'
                '<div class="xinyu-topbar-label">A02 Dashboard</div>'
                f'<h1 class="xinyu-topbar-title">欢迎回来，{display_name}</h1>'
                '<p class="xinyu-topbar-copy">'
                "管理员 JWT 会话已生效，当前页面作为 11.1 的总览占位壳，"
                "11.2 将继续接入真实 KPI 指标与导航。"
                "</p>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        if st.button("退出登录", use_container_width=True):
            clear_admin_session(st.session_state)
            set_admin_auth_error(st.session_state, "已退出当前管理员会话。")
            st.rerun()

    render_admin_identity_card(admin_profile, role_code=role_code)
    render_dashboard_placeholders()


def render_admin_identity_card(
    admin_profile: dict[str, Any],
    *,
    role_code: str,
) -> None:
    """Render the current authenticated admin metadata panel."""
    with st.container(border=False):
        st.caption("当前管理员会话")
        col1, col2, col3 = st.columns(3)
        col1.metric("管理员账号", str(admin_profile.get("username") or "--"))
        col2.metric("角色", role_code)
        col3.metric(
            "最近登录",
            str(admin_profile.get("last_login_at") or "本次会话已建立"),
        )


def render_dashboard_placeholders() -> None:
    """Render the A02 summary placeholders until 11.2 delivers real KPI data."""
    st.caption("A02 总览占位")
    columns = st.columns(4)
    placeholders = (
        ("--", "待复核工单"),
        ("--", "高风险工单"),
        ("--", "重点关注人数"),
        ("--", "已发布帖子数"),
    )
    for column, (value, label) in zip(columns, placeholders, strict=True):
        with column:
            st.markdown(
                (
                    '<div class="xinyu-placeholder-card">'
                    f'<div class="xinyu-placeholder-kpi">{value}</div>'
                    f'<div class="xinyu-placeholder-label">{label}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
    st.info("总览 KPI、导航与真实后台数据将在 IMPLEMENTATION_PLAN.md 步骤 11.2 继续接入。")


if __name__ == "__main__":
    main()
