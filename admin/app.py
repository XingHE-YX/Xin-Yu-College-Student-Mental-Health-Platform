"""Streamlit admin console entrypoint."""

from __future__ import annotations

from datetime import datetime
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
    """Render the administrator login flow and A02 overview page."""
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

    render_dashboard_page(api_client)


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


def render_dashboard_page(api_client: AdminApiClient) -> None:
    """Render the authenticated A02 dashboard with live summary data."""
    admin_profile = get_admin_profile(st.session_state) or {}
    display_name = str(admin_profile.get("display_name") or "管理员")
    role_code = str(admin_profile.get("role_code") or "platform_admin")
    summary, load_error = load_dashboard_summary(api_client)

    left, right = st.columns([0.76, 0.24], vertical_alignment="center")
    with left:
        topbar_copy = (
            "总览页已接入真实 API，当前展示待复核、高风险工单、重点关注与树洞发布概况。"
            if summary is not None
            else "后台会话仍有效，但本次未能加载实时总览数据。可立即刷新重试。"
        )
        st.markdown(
            (
                '<div class="xinyu-topbar">'
                '<div class="xinyu-topbar-label">A02 Dashboard</div>'
                f'<div class="xinyu-sync-chip">数据快照（UTC）· {format_dashboard_timestamp(summary.get("generated_at") if summary else None)}</div>'
                f'<h1 class="xinyu-topbar-title">欢迎回来，{display_name}</h1>'
                f'<p class="xinyu-topbar-copy">{topbar_copy}</p>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        action_left, action_right = st.columns(2)
        with action_left:
            if st.button("刷新总览", use_container_width=True):
                st.rerun()
        with action_right:
            if st.button("退出登录", use_container_width=True):
                clear_admin_session(st.session_state)
                set_admin_auth_error(st.session_state, "已退出当前管理员会话。")
                st.rerun()

    render_admin_identity_card(admin_profile, role_code=role_code)
    if load_error:
        st.error(load_error)
    if summary is None:
        render_dashboard_unavailable_state()
        return

    render_dashboard_kpis(summary["kpis"])
    render_dashboard_stats(summary["stats"])
    render_dashboard_navigation(summary)


def load_dashboard_summary(
    api_client: AdminApiClient,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch the live dashboard summary or normalize recoverable failures."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return None, "当前管理员会话不存在，请重新登录。"

    try:
        return api_client.get_dashboard_summary(access_token=access_token), None
    except AdminApiRequestError as exc:
        if exc.status_code in {401, 403}:
            clear_admin_session(st.session_state)
            if exc.code == "ADMIN_ACCOUNT_INACTIVE" or exc.status_code == 403:
                set_admin_auth_error(st.session_state, "当前账户已被禁用，暂时无法访问后台。")
            else:
                set_admin_auth_error(st.session_state, "管理员会话已失效，请重新登录。")
            st.rerun()
        return None, f"后台总览请求失败：{exc.message}"
    except AdminApiClientError as exc:
        return None, str(exc)


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


def render_dashboard_unavailable_state() -> None:
    """Render the fallback state when the dashboard summary cannot be loaded."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">总览数据暂不可用</div>'
            '<p class="xinyu-empty-copy">'
            "JWT 会话仍已建立，但实时统计暂时无法加载。"
            "你可以刷新重试，或在后端恢复后重新进入后台。"
            "</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_dashboard_kpis(kpis: dict[str, Any]) -> None:
    """Render the primary KPI row for the A02 dashboard."""
    st.caption("A02 总览 KPI")
    columns = st.columns(4)
    cards = (
        (
            int(kpis.get("pending_review_count", 0)),
            "待复核工单",
            "按 `pending_review` 状态统计",
            "warning",
        ),
        (
            int(kpis.get("open_high_risk_case_count", 0)),
            "高风险工单",
            f"其中已确认 {int(kpis.get('confirmed_high_risk_count', 0))}",
            "danger",
        ),
        (
            int(kpis.get("focus_student_count", 0)),
            "重点关注人数",
            "按活跃关注学生去重",
            "brand",
        ),
        (
            int(kpis.get("published_post_count", 0)),
            "已发布帖子数",
            "当前广场公开可见内容",
            "neutral",
        ),
    )
    for column, (value, label, meta, tone) in zip(columns, cards, strict=True):
        with column:
            st.markdown(
                build_kpi_card_html(value=value, label=label, meta=meta, tone=tone),
                unsafe_allow_html=True,
            )


def render_dashboard_stats(stats: dict[str, Any]) -> None:
    """Render the secondary operations snapshot cards below the KPI row."""
    st.caption("基础统计卡片")
    columns = st.columns(4)
    cards = (
        (
            int(stats.get("highest_priority_pending_count", 0)),
            "最高优先级待处理",
            "优先进入 A03 复核队列",
        ),
        (
            int(stats.get("blocked_post_count", 0)),
            "已拦截帖子",
            "高风险或违规内容不会进入广场",
        ),
        (
            int(stats.get("high_risk_student_count", 0)),
            "高风险学生档案",
            "按 `student_users.risk_status=high` 统计",
        ),
        (
            int(stats.get("questionnaire_submission_count", 0)),
            "量表提交总数",
            "包含全部历史测评提交记录",
        ),
    )
    for column, (value, label, meta) in zip(columns, cards, strict=True):
        with column:
            st.markdown(
                build_stat_card_html(value=value, label=label, meta=meta),
                unsafe_allow_html=True,
            )


def render_dashboard_navigation(summary: dict[str, Any]) -> None:
    """Render the A02 module entry cards that lead into later admin pages."""
    kpis = summary["kpis"]
    stats = summary["stats"]
    st.caption("模块入口")
    top_row = st.columns(2)
    bottom_row = st.columns(2)
    cards = (
        (
            "A03",
            "预警队列",
            "按优先级处理待复核案例，并进入 A04 详情完成人工复核。",
            f"待复核 {int(kpis.get('pending_review_count', 0))} · 最高优先级 {int(stats.get('highest_priority_pending_count', 0))}",
            "11.3 下一步",
        ),
        (
            "A05",
            "帖子管理",
            "查看已发布与被拦截的树洞内容，后续支持隐藏与恢复。",
            f"已发布 {int(kpis.get('published_post_count', 0))} · 已拦截 {int(stats.get('blocked_post_count', 0))}",
            "11.4 下一步",
        ),
        (
            "A06",
            "用户目录",
            "按脱敏身份查看重点关注与高风险档案，后续支持敏感信息受控展开。",
            f"重点关注 {int(kpis.get('focus_student_count', 0))} · 高风险档案 {int(stats.get('high_risk_student_count', 0))}",
            "11.5 后续",
        ),
        (
            "A07",
            "审计日志",
            "跟踪后台敏感查看、人工复核和模拟通知等关键操作。",
            "管理员登录已纳入审计，后续补充筛选与查看页。",
            "11.5 后续",
        ),
    )
    for column, (step, title, copy, metric, status_label) in zip(
        (*top_row, *bottom_row),
        cards,
        strict=True,
    ):
        with column:
            st.markdown(
                build_navigation_card_html(
                    step=step,
                    title=title,
                    copy=copy,
                    metric=metric,
                    status_label=status_label,
                ),
                unsafe_allow_html=True,
            )


def build_kpi_card_html(
    *,
    value: int,
    label: str,
    meta: str,
    tone: str,
) -> str:
    """Build one primary KPI card with the configured semantic tone."""
    return (
        f'<div class="xinyu-kpi-card xinyu-kpi-{tone}">'
        f'<div class="xinyu-kpi-value">{value}</div>'
        f'<div class="xinyu-kpi-label">{label}</div>'
        f'<div class="xinyu-kpi-meta">{meta}</div>'
        "</div>"
    )


def build_stat_card_html(
    *,
    value: int,
    label: str,
    meta: str,
) -> str:
    """Build one compact secondary stats card."""
    return (
        '<div class="xinyu-stat-card">'
        f'<div class="xinyu-stat-value">{value}</div>'
        f'<div class="xinyu-stat-label">{label}</div>'
        f'<div class="xinyu-stat-meta">{meta}</div>'
        "</div>"
    )


def build_navigation_card_html(
    *,
    step: str,
    title: str,
    copy: str,
    metric: str,
    status_label: str,
) -> str:
    """Build one module entry card for later admin workflow pages."""
    return (
        '<div class="xinyu-nav-card">'
        '<div class="xinyu-nav-header">'
        f'<span class="xinyu-nav-step">{step}</span>'
        f'<span class="xinyu-nav-status">{status_label}</span>'
        "</div>"
        f'<div class="xinyu-nav-title">{title}</div>'
        f'<div class="xinyu-nav-copy">{copy}</div>'
        f'<div class="xinyu-nav-metric">{metric}</div>'
        "</div>"
    )


def format_dashboard_timestamp(raw_value: Any) -> str:
    """Format the API snapshot timestamp for the dashboard header."""
    if isinstance(raw_value, datetime):
        return raw_value.strftime("%Y-%m-%d %H:%M:%S")
    if not isinstance(raw_value, str) or not raw_value:
        return "未同步"

    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return raw_value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    main()
