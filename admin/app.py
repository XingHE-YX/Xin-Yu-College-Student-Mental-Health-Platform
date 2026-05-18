"""Streamlit admin console entrypoint."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import html
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
    clear_selected_alert_detail,
    clear_selected_post_detail,
    clear_selected_user_detail,
    get_admin_access_token,
    get_admin_active_view,
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
from admin.utils.config import get_admin_api_base_url
from admin.utils.styles import build_admin_console_css

VIEW_DASHBOARD = "dashboard"
VIEW_ALERTS = "alerts"
VIEW_POSTS = "posts"
VIEW_USERS = "users"
VIEW_AUDIT = "audit"
VIEW_ANALYTICS = "analytics"
ALERT_STATUS_FILTER_OPTIONS = (
    ("pending_review", "待复核"),
    ("confirmed_pending_intervention", "已确认"),
    ("dismissed_false_positive", "已忽略"),
    ("closed", "已结案"),
)
ALERT_STATUS_LABELS = {code: label for code, label in ALERT_STATUS_FILTER_OPTIONS}
POST_STATUS_FILTER_OPTIONS = (
    ("published", "已发布"),
    ("hidden_by_admin", "管理员隐藏"),
    ("blocked_high_risk", "被拦截"),
    ("deleted_by_user", "已删除"),
)
POST_STATUS_LABELS = {code: label for code, label in POST_STATUS_FILTER_OPTIONS}
USER_RISK_FILTER_OPTIONS = (
    ("all", "全部风险状态"),
    ("high", "高风险"),
    ("watch", "需关注"),
    ("normal", "正常"),
)
USER_RISK_LABELS = {
    "high": "高风险",
    "watch": "需关注",
    "normal": "正常",
}
USER_RISK_TONES = {
    "normal": "success",
    "watch": "warning",
    "high": "danger",
}
RISK_LABELS = {
    "low": "低风险",
    "watch": "需关注",
    "high": "高风险",
}
RISK_TONES = {
    "low": "success",
    "watch": "warning",
    "high": "danger",
}
PRIORITY_LABELS = {
    "highest": "最高优先级",
    "urgent": "紧急",
    "normal": "常规",
}
INTERVENTION_ACTION_LABELS = {
    "confirm_high_risk": "确认高风险",
    "dismiss_false_positive": "标记误报",
    "simulate_contact": "写入模拟通知",
    "add_note": "添加干预记录",
    "close_case": "结案",
}
POST_VISIBILITY_ACTION_LABELS = {
    "hide": "隐藏帖子",
    "keep_hidden": "保持隐藏",
    "restore_publish": "恢复发布",
}
AUDIT_ACTOR_TYPE_LABELS = {
    "admin": "管理员",
    "system": "系统",
    "student": "学生",
}
ANALYTICS_ACTIVITY_METRICS = (
    ("questionnaire_submission_count", "问卷提交", "#2F8F83"),
    ("treehole_post_count", "树洞发帖", "#E89A4A"),
    ("alert_case_count", "新建工单", "#D84C4C"),
)
FEEDBACK_LEVEL_RENDERERS = {
    "success": st.success,
    "error": st.error,
    "info": st.info,
}


def main() -> None:
    """Render the administrator login flow and authenticated console pages."""
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

    render_authenticated_workspace(api_client)


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
            reset_workspace=False,
        )


def render_authenticated_workspace(api_client: AdminApiClient) -> None:
    """Route the authenticated admin workspace to the current active view."""
    active_view = get_admin_active_view(st.session_state)
    if active_view == VIEW_ALERTS:
        render_alert_queue_page(api_client)
        return
    if active_view == VIEW_POSTS:
        render_post_management_page(api_client)
        return
    if active_view == VIEW_USERS:
        render_user_directory_page(api_client)
        return
    if active_view == VIEW_AUDIT:
        render_audit_log_page(api_client)
        return
    if active_view == VIEW_ANALYTICS:
        render_analytics_page(api_client)
        return
    render_dashboard_page(api_client)


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

    left, right = st.columns([0.74, 0.26], vertical_alignment="center")
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
                f'<h1 class="xinyu-topbar-title">欢迎回来，{escape_html(display_name)}</h1>'
                f'<p class="xinyu-topbar-copy">{escape_html(topbar_copy)}</p>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        top_buttons = st.columns(3)
        bottom_buttons = st.columns(3)
        with top_buttons[0]:
            if st.button("进入 A03", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_ALERTS)
                st.rerun()
        with top_buttons[1]:
            if st.button("进入 A05", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_POSTS)
                st.rerun()
        with top_buttons[2]:
            if st.button("进入 A06", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_USERS)
                st.rerun()
        with bottom_buttons[0]:
            if st.button("进入 A07", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_AUDIT)
                st.rerun()
        with bottom_buttons[1]:
            if st.button("进入 A08", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_ANALYTICS)
                st.rerun()
        with bottom_buttons[2]:
            if st.button("刷新总览", use_container_width=True):
                st.rerun()
        if st.button("退出登录", key="dashboard-logout", use_container_width=True):
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


def render_analytics_page(api_client: AdminApiClient) -> None:
    """Render the A08 analytics page using the live 12.1 aggregate snapshot."""
    admin_profile = get_admin_profile(st.session_state) or {}
    display_name = str(admin_profile.get("display_name") or "管理员")
    role_code = str(admin_profile.get("role_code") or "platform_admin")
    analytics, load_error = load_analytics_snapshot(api_client)

    left, right = st.columns([0.74, 0.26], vertical_alignment="center")
    with left:
        topbar_copy = (
            "当前图表直接基于真实聚合接口返回，集中展示风险分布、近 7 天活跃趋势和工单处理状态。"
            if analytics is not None
            else "管理员会话仍有效，但本次未能加载实时统计数据。可立即刷新重试。"
        )
        st.markdown(
            (
                '<div class="xinyu-topbar">'
                '<div class="xinyu-topbar-label">A08 Analytics</div>'
                f'<div class="xinyu-sync-chip">数据快照（UTC）· {format_dashboard_timestamp(analytics.get("generated_at") if analytics else None)}</div>'
                f'<h1 class="xinyu-topbar-title">统计分析看板 · {escape_html(display_name)}</h1>'
                f'<p class="xinyu-topbar-copy">{escape_html(topbar_copy)}</p>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        top_buttons = st.columns(2)
        bottom_buttons = st.columns(3)
        with top_buttons[0]:
            if st.button("返回 A02", key="analytics-back-dashboard", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_DASHBOARD)
                st.rerun()
        with top_buttons[1]:
            if st.button("前往 A03", key="analytics-go-alerts", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_ALERTS)
                st.rerun()
        with bottom_buttons[0]:
            if st.button("前往 A07", key="analytics-go-audit", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_AUDIT)
                st.rerun()
        with bottom_buttons[1]:
            if st.button("刷新统计", key="analytics-refresh", use_container_width=True):
                st.rerun()
        with bottom_buttons[2]:
            if st.button("退出登录", key="analytics-logout", use_container_width=True):
                clear_admin_session(st.session_state)
                set_admin_auth_error(st.session_state, "已退出当前管理员会话。")
                st.rerun()

    render_admin_identity_card(admin_profile, role_code=role_code)
    if load_error:
        st.error(load_error)
    if analytics is None:
        render_dashboard_unavailable_state()
        return

    render_analytics_summary_cards(analytics)

    top_row = st.columns(2, vertical_alignment="top")
    with top_row[0]:
        render_risk_distribution_chart(analytics["risk_distribution"])
    with top_row[1]:
        render_alert_processing_chart(analytics["alert_processing"])

    render_daily_trend_chart(analytics["daily_trends"])


def render_alert_queue_page(api_client: AdminApiClient) -> None:
    """Render the A03 queue page and A04 detail pane in one master-detail workspace."""
    admin_profile = get_admin_profile(st.session_state) or {}
    display_name = str(admin_profile.get("display_name") or "管理员")

    left, right = st.columns([0.76, 0.24], vertical_alignment="center")
    with left:
        st.markdown(
            (
                '<div class="xinyu-topbar">'
                '<div class="xinyu-topbar-label">A03 Alert Queue</div>'
                f'<h1 class="xinyu-topbar-title">人工复核队列 · {escape_html(display_name)}</h1>'
                '<p class="xinyu-topbar-copy">'
                "左侧按优先级处理待复核案例，右侧查看 A04 详情并执行确认、驳回、补记干预或结案。"
                "</p>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        button_columns = st.columns(4)
        with button_columns[0]:
            if st.button("返回 A02", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_DASHBOARD)
                st.rerun()
        with button_columns[1]:
            if st.button("前往 A05", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_POSTS)
                st.rerun()
        with button_columns[2]:
            if st.button("刷新队列", use_container_width=True):
                st.rerun()
        with button_columns[3]:
            if st.button("退出登录", use_container_width=True):
                clear_admin_session(st.session_state)
                set_admin_auth_error(st.session_state, "已退出当前管理员会话。")
                st.rerun()

    render_alert_feedback_banner()
    queue_status = render_alert_filter_control()
    queue_data, load_error = load_alert_queue(api_client, queue_status=queue_status)
    if load_error:
        st.error(load_error)
    if queue_data is None:
        render_dashboard_unavailable_state()
        return

    render_alert_status_overview(queue_data["status_counts"])

    list_column, detail_column = st.columns([0.44, 0.56], vertical_alignment="top")
    with list_column:
        render_alert_queue_list(api_client, queue_data["items"])
    with detail_column:
        render_selected_alert_detail(api_client)


def render_alert_feedback_banner() -> None:
    """Render and clear any transient A03/A04 feedback stored in session state."""
    feedback = pop_admin_alert_feedback(st.session_state)
    if feedback is None:
        return

    level = feedback.get("level", "info")
    message = feedback.get("message", "")
    renderer = FEEDBACK_LEVEL_RENDERERS.get(level, st.info)
    renderer(message)


def render_alert_filter_control() -> str:
    """Render the A03 queue filter selectbox and return the selected status code."""
    if "admin_alert_queue_filter" not in st.session_state:
        st.session_state["admin_alert_queue_filter"] = "pending_review"

    selected_status = st.selectbox(
        "队列状态",
        options=[option[0] for option in ALERT_STATUS_FILTER_OPTIONS],
        format_func=lambda status_code: ALERT_STATUS_LABELS.get(status_code, status_code),
        key="admin_alert_queue_filter",
    )
    st.caption("默认按优先级排序；同优先级下按创建时间倒序。")
    return str(selected_status)


def render_alert_status_overview(status_counts: list[dict[str, Any]]) -> None:
    """Render the four status buckets above the queue list."""
    st.caption("A03 队列状态")
    columns = st.columns(4)
    for column, item in zip(columns, status_counts, strict=True):
        with column:
            st.markdown(
                build_stat_card_html(
                    value=int(item.get("count", 0)),
                    label=ALERT_STATUS_LABELS.get(
                        str(item.get("queue_status", "")),
                        str(item.get("queue_status", "--")),
                    ),
                    meta="当前状态工单数",
                ),
                unsafe_allow_html=True,
            )


def render_alert_queue_list(
    api_client: AdminApiClient,
    alert_items: list[dict[str, Any]],
) -> None:
    """Render the left-side A03 queue cards and open detail on explicit click."""
    st.caption("待处理案例")
    if not alert_items:
        render_queue_empty_state()
        return

    selected_alert_id = get_selected_alert_id(st.session_state)
    for item in alert_items:
        alert_id = int(item["alert_id"])
        is_active = selected_alert_id == alert_id
        st.markdown(
            build_alert_queue_card_html(item, is_active=is_active),
            unsafe_allow_html=True,
        )
        if st.button(
            "打开案例" if not is_active else "当前详情",
            key=f"open-alert-{alert_id}",
            use_container_width=True,
            disabled=is_active,
        ):
            handle_select_alert(api_client, alert_id=alert_id)


def render_selected_alert_detail(api_client: AdminApiClient) -> None:
    """Render the right-side A04 detail pane for the currently selected alert."""
    alert_detail = get_selected_alert_detail(st.session_state)
    if alert_detail is None:
        render_detail_empty_state()
        return

    alert_id = int(alert_detail["alert_id"])
    st.caption(f"A04 预警详情 · #{alert_id}")
    st.markdown(
        build_alert_detail_header_html(alert_detail),
        unsafe_allow_html=True,
    )

    render_alert_student_snapshot(alert_detail["student"])
    render_alert_source_context(api_client, alert_detail)
    render_alert_history_context(alert_detail["history"])
    render_alert_intervention_timeline(alert_detail["intervention_logs"])
    render_alert_action_zone(api_client, alert_detail)


def render_alert_student_snapshot(student: dict[str, Any]) -> None:
    """Render the masked student identity card for A04."""
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">脱敏身份</div>'
            f'<div class="xinyu-section-title">{escape_html(str(student.get("student_label", "--")))}</div>'
            '<div class="xinyu-section-copy">'
            f'手机号：{escape_html(str(student.get("masked_phone", "--")))} · '
            f'风险状态：{escape_html(render_risk_label(str(student.get("risk_status", ""))))} · '
            f'授权：{escape_html(str(student.get("consent_status", "--")))}'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    col1.metric("学院", str(student.get("college_name") or "--"))
    col2.metric("班级", str(student.get("class_name") or "--"))


def render_alert_source_context(
    api_client: AdminApiClient,
    alert_detail: dict[str, Any],
) -> None:
    """Render the source-specific context block inside A04."""
    source = alert_detail["source"]
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">来源上下文</div>'
            f'<div class="xinyu-section-title">{escape_html(str(source.get("kind", "--")).upper())}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    if source.get("kind") == "treehole":
        render_treehole_source_context(api_client, alert_detail)
        return
    render_assessment_source_context(source)


def render_treehole_source_context(
    api_client: AdminApiClient,
    alert_detail: dict[str, Any],
) -> None:
    """Render masked treehole context and explicit raw-content reveal controls."""
    source = alert_detail["source"]
    metadata_columns = st.columns(3)
    metadata_columns[0].metric("匿名昵称", str(source.get("anonymous_name") or "--"))
    metadata_columns[1].metric("发布状态", str(source.get("publish_status") or "--"))
    metadata_columns[2].metric(
        "风险等级",
        render_risk_label(str(source.get("risk_level") or "--")),
    )

    st.markdown(
        build_copy_block_html(
            title="默认展示脱敏内容",
            body=str(source.get("masked_content") or "--"),
            tone="warning",
        ),
        unsafe_allow_html=True,
    )

    ai_analysis = source.get("ai_analysis")
    if isinstance(ai_analysis, dict):
        st.markdown(
            build_ai_analysis_card_html(ai_analysis),
            unsafe_allow_html=True,
        )

    if source.get("full_content_available"):
        with st.expander("查看完整原文（需二次确认）", expanded=bool(source.get("full_content"))):
            confirm_reveal = st.checkbox(
                "我已确认因人工复核需要查看完整原文。",
                key=f"reveal-confirm-{alert_detail['alert_id']}",
            )
            if st.button(
                "展开完整原文",
                key=f"reveal-alert-{alert_detail['alert_id']}",
                use_container_width=True,
            ):
                if not confirm_reveal:
                    set_admin_alert_feedback(
                        st.session_state,
                        {"level": "error", "message": "请先确认查看敏感原文的必要性。"},
                    )
                    st.rerun()
                handle_reveal_alert_content(
                    api_client,
                    alert_id=int(alert_detail["alert_id"]),
                )

            full_content = source.get("full_content")
            if isinstance(full_content, str) and full_content:
                st.markdown(
                    build_copy_block_html(
                        title="完整原文",
                        body=full_content,
                        tone="danger",
                    ),
                    unsafe_allow_html=True,
                )


def render_assessment_source_context(source: dict[str, Any]) -> None:
    """Render questionnaire source details for one assessment-driven alert."""
    metadata_columns = st.columns(4)
    metadata_columns[0].metric(
        "问卷编码",
        str(source.get("questionnaire_code") or "--"),
    )
    metadata_columns[1].metric(
        "风险等级",
        render_risk_label(str(source.get("risk_level") or "--")),
    )
    metadata_columns[2].metric(
        "原始分",
        str(source.get("raw_score") or "--"),
    )
    metadata_columns[3].metric(
        "标准分",
        str(source.get("standardized_score") or "--"),
    )

    st.markdown(
        build_copy_block_html(
            title=str(source.get("questionnaire_name") or "量表结果"),
            body=str(source.get("result_summary") or "--"),
            tone="brand",
        ),
        unsafe_allow_html=True,
    )

    hard_trigger_matches = source.get("hard_trigger_matches") or []
    if hard_trigger_matches:
        trigger_lines = []
        for match in hard_trigger_matches:
            if isinstance(match, dict):
                trigger_lines.append(
                    f"{match.get('reason_code', '--')} · {match.get('question_code', '--')} · 命中值 {match.get('matched_value', '--')}"
                )
        st.markdown(
            build_copy_block_html(
                title="硬触发记录",
                body="\n".join(trigger_lines),
                tone="danger",
            ),
            unsafe_allow_html=True,
        )


def render_alert_history_context(history: dict[str, Any]) -> None:
    """Render history flags and latest questionnaire summaries."""
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">历史测评信息</div>'
            '<div class="xinyu-section-title">最新量表与历史风险标记</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    history_flags = history.get("history_flags") or []
    if history_flags:
        for flag in history_flags:
            if isinstance(flag, dict):
                st.warning(str(flag.get("label") or "--"))
    else:
        st.info("当前没有额外的历史高风险标记。")

    latest_questionnaires = history.get("latest_questionnaires") or []
    if not latest_questionnaires:
        st.caption("暂无历史量表记录。")
        return

    columns = st.columns(2)
    for index, item in enumerate(latest_questionnaires):
        column = columns[index % 2]
        with column:
            st.markdown(
                build_history_item_card_html(item),
                unsafe_allow_html=True,
            )


def render_alert_intervention_timeline(intervention_logs: list[dict[str, Any]]) -> None:
    """Render the A04 intervention timeline newest-first."""
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">处置时间线</div>'
            '<div class="xinyu-section-title">干预记录与模拟通知</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if not intervention_logs:
        st.caption("当前案例尚无人工处置记录。")
        return

    for item in intervention_logs:
        st.markdown(
            build_timeline_item_html(item),
            unsafe_allow_html=True,
        )


def render_alert_action_zone(
    api_client: AdminApiClient,
    alert_detail: dict[str, Any],
) -> None:
    """Render action forms for confirm, dismiss, add-note, and close workflows."""
    permissions = alert_detail["action_permissions"]
    alert_id = int(alert_detail["alert_id"])
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">处置动作区</div>'
            '<div class="xinyu-section-title">按当前状态执行人工复核</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    if permissions.get("can_confirm") or permissions.get("can_dismiss"):
        action_left, action_right = st.columns(2)
        if permissions.get("can_confirm"):
            with action_left:
                with st.form(f"confirm-alert-form-{alert_id}", clear_on_submit=False):
                    st.markdown("**确认高风险**")
                    review_note = st.text_area(
                        "复核结论",
                        placeholder="例如：人工复核确认存在强烈自伤表述，需要继续跟进。",
                        key=f"confirm-review-note-{alert_id}",
                    )
                    intervention_note = st.text_area(
                        "模拟通知说明",
                        placeholder="例如：已记录给辅导员的模拟联系说明。",
                        key=f"confirm-intervention-note-{alert_id}",
                    )
                    submitted = st.form_submit_button("确认高风险", use_container_width=True)
                if submitted:
                    handle_confirm_alert(
                        api_client,
                        alert_id=alert_id,
                        review_note=review_note,
                        intervention_note=intervention_note,
                    )
        if permissions.get("can_dismiss"):
            with action_right:
                with st.form(f"dismiss-alert-form-{alert_id}", clear_on_submit=False):
                    st.markdown("**标记误报**")
                    review_note = st.text_area(
                        "驳回说明",
                        placeholder="例如：上下文不足以支撑高风险判断。",
                        key=f"dismiss-review-note-{alert_id}",
                    )
                    submitted = st.form_submit_button("标记误报", use_container_width=True)
                if submitted:
                    handle_dismiss_alert(
                        api_client,
                        alert_id=alert_id,
                        review_note=review_note,
                    )

    lower_left, lower_right = st.columns(2)
    if permissions.get("can_add_note"):
        with lower_left:
            with st.form(f"add-note-form-{alert_id}", clear_on_submit=False):
                st.markdown("**添加干预记录**")
                action_note = st.text_area(
                    "干预备注",
                    placeholder="例如：已安排次日回访，等待学生线下到访。",
                    key=f"add-note-action-note-{alert_id}",
                )
                submitted = st.form_submit_button("写入干预记录", use_container_width=True)
            if submitted:
                handle_add_alert_note(
                    api_client,
                    alert_id=alert_id,
                    action_note=action_note,
                )

    if permissions.get("can_close"):
        with lower_right:
            with st.form(f"close-alert-form-{alert_id}", clear_on_submit=False):
                st.markdown("**结案**")
                action_note = st.text_area(
                    "结案说明",
                    placeholder="例如：线下跟进完成，当前案例转入常规观察。",
                    key=f"close-action-note-{alert_id}",
                )
                submitted = st.form_submit_button("结案", use_container_width=True)
            if submitted:
                handle_close_alert(
                    api_client,
                    alert_id=alert_id,
                    action_note=action_note,
                )


def render_post_management_page(api_client: AdminApiClient) -> None:
    """Render the A05 post-management page with list/detail workspace layout."""
    admin_profile = get_admin_profile(st.session_state) or {}
    display_name = str(admin_profile.get("display_name") or "管理员")

    left, right = st.columns([0.76, 0.24], vertical_alignment="center")
    with left:
        st.markdown(
            (
                '<div class="xinyu-topbar">'
                '<div class="xinyu-topbar-label">A05 Post Management</div>'
                f'<h1 class="xinyu-topbar-title">树洞帖子管理 · {escape_html(display_name)}</h1>'
                '<p class="xinyu-topbar-copy">'
                "左侧按状态查看帖子，右侧在脱敏前提下展开详情、查看原文，并执行隐藏或恢复发布动作。"
                "</p>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        button_columns = st.columns(4)
        with button_columns[0]:
            if st.button("返回 A02", key="posts-back-dashboard", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_DASHBOARD)
                st.rerun()
        with button_columns[1]:
            if st.button("前往 A03", key="posts-go-alerts", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_ALERTS)
                st.rerun()
        with button_columns[2]:
            if st.button("刷新帖子", key="posts-refresh", use_container_width=True):
                st.rerun()
        with button_columns[3]:
            if st.button("退出登录", key="posts-logout", use_container_width=True):
                clear_admin_session(st.session_state)
                set_admin_auth_error(st.session_state, "已退出当前管理员会话。")
                st.rerun()

    render_alert_feedback_banner()
    publish_status = render_post_filter_control()
    post_data, load_error = load_post_list(api_client, publish_status=publish_status)
    if load_error:
        st.error(load_error)
    if post_data is None:
        render_dashboard_unavailable_state()
        return

    render_post_status_overview(post_data["status_counts"])

    list_column, detail_column = st.columns([0.44, 0.56], vertical_alignment="top")
    with list_column:
        render_post_management_list(api_client, post_data["items"])
    with detail_column:
        render_selected_post_detail(api_client)


def render_post_filter_control() -> str:
    """Render the A05 post-status filter selectbox and return the selected status."""
    if "admin_post_status_filter" not in st.session_state:
        st.session_state["admin_post_status_filter"] = "published"

    selected_status = st.selectbox(
        "帖子状态",
        options=[option[0] for option in POST_STATUS_FILTER_OPTIONS],
        format_func=lambda status_code: POST_STATUS_LABELS.get(status_code, status_code),
        key="admin_post_status_filter",
    )
    st.caption("默认按最新可见活动时间倒序排列，可查看已发布、被拦截、隐藏和软删除内容。")
    return str(selected_status)


def render_post_status_overview(status_counts: list[dict[str, Any]]) -> None:
    """Render the four status buckets above the A05 post list."""
    st.caption("A05 帖子状态")
    columns = st.columns(4)
    for column, item in zip(columns, status_counts, strict=True):
        with column:
            st.markdown(
                build_stat_card_html(
                    value=int(item.get("count", 0)),
                    label=POST_STATUS_LABELS.get(
                        str(item.get("publish_status", "")),
                        str(item.get("publish_status", "--")),
                    ),
                    meta="当前状态帖子数",
                ),
                unsafe_allow_html=True,
            )


def render_post_management_list(
    api_client: AdminApiClient,
    post_items: list[dict[str, Any]],
) -> None:
    """Render the left-side A05 post cards and open detail on explicit click."""
    st.caption("帖子列表")
    if not post_items:
        render_post_empty_state()
        return

    selected_post_id = get_selected_post_id(st.session_state)
    for item in post_items:
        post_id = int(item["post_id"])
        is_active = selected_post_id == post_id
        st.markdown(
            build_post_queue_card_html(item, is_active=is_active),
            unsafe_allow_html=True,
        )
        if st.button(
            "打开帖子" if not is_active else "当前详情",
            key=f"open-post-{post_id}",
            use_container_width=True,
            disabled=is_active,
        ):
            handle_select_post(api_client, post_id=post_id)


def render_selected_post_detail(api_client: AdminApiClient) -> None:
    """Render the right-side A05 detail pane for the currently selected post."""
    post_detail = get_selected_post_detail(st.session_state)
    if post_detail is None:
        render_post_detail_empty_state()
        return

    post_id = int(post_detail["post_id"])
    st.caption(f"A05 帖子详情 · #{post_id}")
    st.markdown(
        build_post_detail_header_html(post_detail),
        unsafe_allow_html=True,
    )

    render_post_owner_snapshot(post_detail["student"])
    render_post_content_context(api_client, post_detail)
    render_post_reaction_summary(post_detail["reactions"])
    render_post_ai_analysis(post_detail["ai_analysis"])
    render_post_alert_case_summary(post_detail.get("alert_case_summary"))
    render_post_action_zone(api_client, post_detail)


def render_post_owner_snapshot(student: dict[str, Any]) -> None:
    """Render the masked owner identity card for A05."""
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">发帖人身份</div>'
            f'<div class="xinyu-section-title">{escape_html(str(student.get("student_label", "--")))}</div>'
            '<div class="xinyu-section-copy">'
            f'手机号：{escape_html(str(student.get("masked_phone", "--")))} · '
            f'风险状态：{escape_html(render_risk_label(str(student.get("risk_status", ""))))}'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    col1.metric("学院", str(student.get("college_name") or "--"))
    col2.metric("班级", str(student.get("class_name") or "--"))


def render_post_content_context(
    api_client: AdminApiClient,
    post_detail: dict[str, Any],
) -> None:
    """Render masked post content and the explicit raw-content reveal flow."""
    content = post_detail["content"]
    metadata_columns = st.columns(3)
    metadata_columns[0].metric("匿名昵称", str(post_detail.get("anonymous_name") or "--"))
    metadata_columns[1].metric(
        "发布状态",
        str(post_detail.get("publish_status_label") or "--"),
    )
    metadata_columns[2].metric(
        "风险等级",
        render_risk_label(str(post_detail.get("risk_level") or "--")),
    )

    st.markdown(
        build_copy_block_html(
            title="默认展示脱敏内容",
            body=str(content.get("masked_content") or "--"),
            tone="warning",
        ),
        unsafe_allow_html=True,
    )

    if content.get("full_content_available"):
        with st.expander(
            "查看完整原文（需二次确认）",
            expanded=bool(content.get("full_content")),
        ):
            confirm_reveal = st.checkbox(
                "我已确认因内容治理或人工复核需要查看完整原文。",
                key=f"reveal-post-confirm-{post_detail['post_id']}",
            )
            if st.button(
                "展开完整原文",
                key=f"reveal-post-{post_detail['post_id']}",
                use_container_width=True,
            ):
                if not confirm_reveal:
                    set_admin_alert_feedback(
                        st.session_state,
                        {"level": "error", "message": "请先确认查看完整原文的必要性。"},
                    )
                    st.rerun()
                handle_reveal_post_content(
                    api_client,
                    post_id=int(post_detail["post_id"]),
                )

            full_content = content.get("full_content")
            if isinstance(full_content, str) and full_content:
                st.markdown(
                    build_copy_block_html(
                        title="完整原文",
                        body=full_content,
                        tone="danger",
                    ),
                    unsafe_allow_html=True,
                )


def render_post_reaction_summary(reactions: list[dict[str, Any]]) -> None:
    """Render preset support reaction totals for the selected managed post."""
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">互动概况</div>'
            '<div class="xinyu-section-title">预设支持反应统计</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    columns = st.columns(3)
    for column, item in zip(columns, reactions, strict=True):
        column.metric(str(item.get("label") or "--"), str(item.get("count") or 0))


def render_post_ai_analysis(ai_analysis: dict[str, Any] | None) -> None:
    """Render the latest AI moderation analysis for the selected post."""
    if ai_analysis is None:
        st.info("该帖子当前没有可用的 AI 分析记录。")
        return

    st.markdown(
        build_ai_analysis_card_html(ai_analysis),
        unsafe_allow_html=True,
    )


def render_post_alert_case_summary(alert_case_summary: dict[str, Any] | None) -> None:
    """Render the linked alert-case summary for blocked posts when one exists."""
    if alert_case_summary is None:
        return

    st.markdown(
        (
            '<div class="xinyu-detail-card">'
            '<div class="xinyu-detail-title">关联预警工单</div>'
            f'<div class="xinyu-detail-copy">工单 #{int(alert_case_summary.get("alert_id", 0))} · '
            f'{escape_html(ALERT_STATUS_LABELS.get(str(alert_case_summary.get("queue_status", "")), str(alert_case_summary.get("queue_status", "--"))))}'
            f' · {escape_html(PRIORITY_LABELS.get(str(alert_case_summary.get("review_priority", "")), str(alert_case_summary.get("review_priority", "--"))))}</div>'
            f'<div class="xinyu-detail-foot">最新复核说明：{escape_html(str(alert_case_summary.get("review_note") or "暂无"))}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_post_action_zone(
    api_client: AdminApiClient,
    post_detail: dict[str, Any],
) -> None:
    """Render visibility action controls for the selected managed post."""
    permissions = post_detail["action_permissions"]
    post_id = int(post_detail["post_id"])
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">内容治理动作</div>'
            '<div class="xinyu-section-title">按当前状态执行隐藏、保持隐藏或恢复发布</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    columns = st.columns(3)
    with columns[0]:
        if permissions.get("can_hide") and st.button(
            POST_VISIBILITY_ACTION_LABELS["hide"],
            key=f"hide-post-{post_id}",
            use_container_width=True,
        ):
            handle_update_post_visibility(
                api_client,
                post_id=post_id,
                action="hide",
            )
    with columns[1]:
        if permissions.get("can_keep_hidden") and st.button(
            POST_VISIBILITY_ACTION_LABELS["keep_hidden"],
            key=f"keep-hidden-post-{post_id}",
            use_container_width=True,
        ):
            handle_update_post_visibility(
                api_client,
                post_id=post_id,
                action="keep_hidden",
            )
    with columns[2]:
        if permissions.get("can_restore_publish") and st.button(
            POST_VISIBILITY_ACTION_LABELS["restore_publish"],
            key=f"restore-post-{post_id}",
            use_container_width=True,
        ):
            handle_update_post_visibility(
                api_client,
                post_id=post_id,
                action="restore_publish",
            )


def render_user_directory_page(api_client: AdminApiClient) -> None:
    """Render the A06 user-directory page with list/detail workspace layout."""
    admin_profile = get_admin_profile(st.session_state) or {}
    display_name = str(admin_profile.get("display_name") or "管理员")

    left, right = st.columns([0.76, 0.24], vertical_alignment="center")
    with left:
        st.markdown(
            (
                '<div class="xinyu-topbar">'
                '<div class="xinyu-topbar-label">A06 User Directory</div>'
                f'<h1 class="xinyu-topbar-title">用户目录 · {escape_html(display_name)}</h1>'
                '<p class="xinyu-topbar-copy">'
                "左侧默认展示脱敏用户列表，右侧仅在你显式打开详情并二次确认后展示完整手机号与风险档案。"
                "</p>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        button_columns = st.columns(5)
        with button_columns[0]:
            if st.button("返回 A02", key="users-back-dashboard", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_DASHBOARD)
                st.rerun()
        with button_columns[1]:
            if st.button("前往 A05", key="users-go-posts", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_POSTS)
                st.rerun()
        with button_columns[2]:
            if st.button("前往 A07", key="users-go-audit", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_AUDIT)
                st.rerun()
        with button_columns[3]:
            if st.button("刷新目录", key="users-refresh", use_container_width=True):
                st.rerun()
        with button_columns[4]:
            if st.button("退出登录", key="users-logout", use_container_width=True):
                clear_admin_session(st.session_state)
                set_admin_auth_error(st.session_state, "已退出当前管理员会话。")
                st.rerun()

    render_alert_feedback_banner()
    risk_status = render_user_filter_control()
    user_data, load_error = load_user_directory(
        api_client,
        risk_status=risk_status,
    )
    if load_error:
        st.error(load_error)
    if user_data is None:
        render_dashboard_unavailable_state()
        return

    render_user_status_overview(user_data["status_counts"])
    list_column, detail_column = st.columns([0.44, 0.56], vertical_alignment="top")
    with list_column:
        render_user_directory_list(api_client, user_data["items"])
    with detail_column:
        render_selected_user_detail(api_client)


def render_audit_log_page(api_client: AdminApiClient) -> None:
    """Render the A07 audit-log page with filters and formatted records."""
    admin_profile = get_admin_profile(st.session_state) or {}
    display_name = str(admin_profile.get("display_name") or "管理员")

    left, right = st.columns([0.76, 0.24], vertical_alignment="center")
    with left:
        st.markdown(
            (
                '<div class="xinyu-topbar">'
                '<div class="xinyu-topbar-label">A07 Audit Logs</div>'
                f'<h1 class="xinyu-topbar-title">审计日志 · {escape_html(display_name)}</h1>'
                '<p class="xinyu-topbar-copy">'
                "按操作者、动作编码、目标类型和日期范围筛选后台敏感操作记录。"
                "</p>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        button_columns = st.columns(5)
        with button_columns[0]:
            if st.button("返回 A02", key="audit-back-dashboard", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_DASHBOARD)
                st.rerun()
        with button_columns[1]:
            if st.button("前往 A03", key="audit-go-alerts", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_ALERTS)
                st.rerun()
        with button_columns[2]:
            if st.button("前往 A06", key="audit-go-users", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_USERS)
                st.rerun()
        with button_columns[3]:
            if st.button("刷新审计", key="audit-refresh", use_container_width=True):
                st.rerun()
        with button_columns[4]:
            if st.button("退出登录", key="audit-logout", use_container_width=True):
                clear_admin_session(st.session_state)
                set_admin_auth_error(st.session_state, "已退出当前管理员会话。")
                st.rerun()

    render_alert_feedback_banner()
    ensure_audit_filter_state()
    audit_data, load_error = load_audit_log_snapshot(api_client)
    if load_error:
        st.error(load_error)
    if audit_data is None:
        render_dashboard_unavailable_state()
        return

    render_audit_filter_controls(audit_data)
    st.metric("当前筛选命中记录", int(audit_data.get("filtered_count", 0)))
    render_audit_log_records(audit_data["records"])


def render_user_filter_control() -> str | None:
    """Render the A06 risk-status filter and return the selected backend value."""
    if "admin_user_risk_filter" not in st.session_state:
        st.session_state["admin_user_risk_filter"] = "all"

    selected_status = st.selectbox(
        "风险状态",
        options=[option[0] for option in USER_RISK_FILTER_OPTIONS],
        format_func=lambda status_code: dict(USER_RISK_FILTER_OPTIONS).get(
            status_code,
            status_code,
        ),
        key="admin_user_risk_filter",
    )
    st.caption("默认按风险等级高到低排序，再按最近更新时间倒序。")
    return None if selected_status == "all" else str(selected_status)


def render_user_status_overview(status_counts: list[dict[str, Any]]) -> None:
    """Render the A06 risk-status buckets above the user list."""
    st.caption("A06 风险状态分布")
    columns = st.columns(3)
    for column, item in zip(columns, status_counts, strict=True):
        risk_status = str(item.get("risk_status", ""))
        with column:
            st.markdown(
                build_stat_card_html(
                    value=int(item.get("count", 0)),
                    label=USER_RISK_LABELS.get(risk_status, risk_status),
                    meta="当前学生人数",
                ),
                unsafe_allow_html=True,
            )


def render_user_directory_list(
    api_client: AdminApiClient,
    user_items: list[dict[str, Any]],
) -> None:
    """Render the left-side A06 user cards and open detail on explicit click."""
    st.caption("脱敏用户列表")
    if not user_items:
        render_user_empty_state()
        return

    selected_user_id = get_selected_user_id(st.session_state)
    for item in user_items:
        student_id = int(item["student_id"])
        is_active = selected_user_id == student_id
        st.markdown(
            build_user_directory_card_html(item, is_active=is_active),
            unsafe_allow_html=True,
        )
        if st.button(
            "查看详情" if not is_active else "当前详情",
            key=f"open-user-{student_id}",
            use_container_width=True,
            disabled=is_active,
        ):
            handle_select_user(api_client, student_id=student_id)


def render_selected_user_detail(api_client: AdminApiClient) -> None:
    """Render the right-side A06 detail pane for the currently selected student."""
    user_detail = get_selected_user_detail(st.session_state)
    if user_detail is None:
        render_user_detail_empty_state()
        return

    student_id = int(user_detail["student_id"])
    st.caption(f"A06 用户详情 · {escape_html(str(user_detail.get('student_label') or f'STU-{student_id:06d}'))}")
    st.markdown(
        build_user_detail_header_html(user_detail),
        unsafe_allow_html=True,
    )

    render_user_identity_summary(api_client, user_detail)
    render_user_risk_archive(user_detail)


def render_user_identity_summary(
    api_client: AdminApiClient,
    user_detail: dict[str, Any],
) -> None:
    """Render the identity and phone-reveal section for the selected student."""
    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">身份与授权</div>'
            f'<div class="xinyu-section-title">{escape_html(str(user_detail.get("student_label") or "--"))}</div>'
            '<div class="xinyu-section-copy">'
            f'手机号：{escape_html(str(user_detail.get("masked_phone") or "--"))} · '
            f'授权：{escape_html(str(user_detail.get("consent_status") or "--"))} · '
            f'演示账号：{escape_html("是" if user_detail.get("is_demo") else "否")}'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    info_columns = st.columns(4)
    info_columns[0].metric("学院", str(user_detail.get("college_name") or "--"))
    info_columns[1].metric("班级", str(user_detail.get("class_name") or "--"))
    info_columns[2].metric("最新登录", format_dashboard_timestamp(user_detail.get("last_login_at")))
    info_columns[3].metric("最近更新", format_dashboard_timestamp(user_detail.get("updated_at")))

    with st.expander("查看完整手机号（需二次确认）", expanded=bool(user_detail.get("full_phone"))):
        confirm_reveal = st.checkbox(
            "我已确认因人工复核或风险干预需要查看完整手机号。",
            key=f"reveal-phone-confirm-{user_detail['student_id']}",
        )
        if st.button(
            "展开完整手机号",
            key=f"reveal-phone-{user_detail['student_id']}",
            use_container_width=True,
        ):
            if not confirm_reveal:
                set_admin_alert_feedback(
                    st.session_state,
                    {"level": "error", "message": "请先确认查看完整手机号的必要性。"},
                )
                st.rerun()
            handle_reveal_user_phone(
                api_client,
                student_id=int(user_detail["student_id"]),
            )

        full_phone = user_detail.get("full_phone")
        if isinstance(full_phone, str) and full_phone:
            st.markdown(
                build_copy_block_html(
                    title="完整手机号",
                    body=full_phone,
                    tone="danger",
                ),
                unsafe_allow_html=True,
            )


def render_user_risk_archive(user_detail: dict[str, Any]) -> None:
    """Render risk-archive summaries for the selected student."""
    summary = user_detail["summary"]
    columns = st.columns(3)
    columns[0].metric("活跃重点关注", int(summary.get("active_focus_count", 0)))
    columns[1].metric("开放工单", int(summary.get("open_alert_count", 0)))
    columns[2].metric("树洞总数", int(summary.get("treehole_post_count", 0)))

    st.markdown(
        (
            '<div class="xinyu-section-card">'
            '<div class="xinyu-section-label">风险档案</div>'
            '<div class="xinyu-section-title">最新量表、树洞与重点关注摘要</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    latest_questionnaires = user_detail.get("latest_questionnaires") or []
    if latest_questionnaires:
        questionnaire_columns = st.columns(2)
        for index, item in enumerate(latest_questionnaires):
            with questionnaire_columns[index % 2]:
                st.markdown(
                    build_user_questionnaire_item_html(item),
                    unsafe_allow_html=True,
                )
    else:
        st.caption("暂无量表记录。")

    latest_posts = user_detail.get("latest_posts") or []
    if latest_posts:
        post_columns = st.columns(2)
        for index, item in enumerate(latest_posts):
            with post_columns[index % 2]:
                st.markdown(
                    build_user_post_item_html(item),
                    unsafe_allow_html=True,
                )

    focus_entries = user_detail.get("focus_entries") or []
    if focus_entries:
        st.markdown(
            (
                '<div class="xinyu-section-card">'
                '<div class="xinyu-section-label">重点关注记录</div>'
                '<div class="xinyu-section-title">最新重点关注原因</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        for item in focus_entries:
            st.markdown(
                build_focus_entry_card_html(item),
                unsafe_allow_html=True,
            )

    recent_alert_cases = user_detail.get("recent_alert_cases") or []
    if recent_alert_cases:
        st.markdown(
            (
                '<div class="xinyu-section-card">'
                '<div class="xinyu-section-label">预警工单</div>'
                '<div class="xinyu-section-title">最近预警工单摘要</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        for item in recent_alert_cases:
            st.markdown(
                build_recent_alert_summary_html(item),
                unsafe_allow_html=True,
            )


def ensure_audit_filter_state() -> None:
    """Ensure default A07 filter widget state is initialized once."""
    st.session_state.setdefault("admin_audit_actor_key", "all")
    st.session_state.setdefault("admin_audit_action_code", "all")
    st.session_state.setdefault("admin_audit_target_type", "all")
    st.session_state.setdefault("admin_audit_date_from", None)
    st.session_state.setdefault("admin_audit_date_to", None)


def render_audit_filter_controls(audit_data: dict[str, Any]) -> None:
    """Render the A07 audit filter bar using backend-provided option metadata."""
    actor_options = audit_data.get("actor_options") or []
    actor_key_options = ["all", *[build_actor_filter_key(item) for item in actor_options]]
    actor_label_by_key = {
        "all": "全部操作者",
        **{
            build_actor_filter_key(item): str(item.get("label") or "--")
            for item in actor_options
        },
    }
    action_code_options = ["all", *(audit_data.get("action_code_options") or [])]
    target_type_options = ["all", *(audit_data.get("target_type_options") or [])]

    if st.session_state.get("admin_audit_actor_key") not in actor_key_options:
        st.session_state["admin_audit_actor_key"] = "all"
    if st.session_state.get("admin_audit_action_code") not in action_code_options:
        st.session_state["admin_audit_action_code"] = "all"
    if st.session_state.get("admin_audit_target_type") not in target_type_options:
        st.session_state["admin_audit_target_type"] = "all"

    filter_columns = st.columns(5)
    filter_columns[0].selectbox(
        "操作者",
        options=actor_key_options,
        format_func=lambda key: actor_label_by_key.get(key, key),
        key="admin_audit_actor_key",
    )
    filter_columns[1].selectbox(
        "操作类型",
        options=action_code_options,
        format_func=lambda action_code: "全部操作类型" if action_code == "all" else action_code,
        key="admin_audit_action_code",
    )
    filter_columns[2].selectbox(
        "目标类型",
        options=target_type_options,
        format_func=lambda target: "全部目标类型" if target == "all" else target,
        key="admin_audit_target_type",
    )
    filter_columns[3].date_input(
        "起始日期",
        key="admin_audit_date_from",
    )
    filter_columns[4].date_input(
        "结束日期",
        key="admin_audit_date_to",
    )


def render_audit_log_records(records: list[dict[str, Any]]) -> None:
    """Render the filtered A07 audit records newest-first."""
    st.caption("A07 审计记录")
    if not records:
        render_audit_empty_state()
        return

    for record in records:
        st.markdown(
            build_audit_record_card_html(record),
            unsafe_allow_html=True,
        )


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
        return None, normalize_admin_request_error(exc)
    except AdminApiClientError as exc:
        return None, str(exc)


def load_analytics_snapshot(
    api_client: AdminApiClient,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch the live A08 analytics payload or normalize recoverable failures."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return None, "当前管理员会话不存在，请重新登录。"

    try:
        return api_client.get_analytics_trends(access_token=access_token), None
    except AdminApiRequestError as exc:
        return None, normalize_admin_request_error(exc)
    except AdminApiClientError as exc:
        return None, str(exc)


def load_alert_queue(
    api_client: AdminApiClient,
    *,
    queue_status: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch the filtered alert queue payload for the A03 master list."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return None, "当前管理员会话不存在，请重新登录。"

    try:
        return api_client.list_alerts(
            access_token=access_token,
            queue_status=queue_status,
        ), None
    except AdminApiRequestError as exc:
        return None, normalize_admin_request_error(exc)
    except AdminApiClientError as exc:
        return None, str(exc)


def load_post_list(
    api_client: AdminApiClient,
    *,
    publish_status: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch the filtered A05 post-management payload."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return None, "当前管理员会话不存在，请重新登录。"

    try:
        return api_client.list_posts(
            access_token=access_token,
            publish_status=publish_status,
        ), None
    except AdminApiRequestError as exc:
        return None, normalize_admin_request_error(exc)
    except AdminApiClientError as exc:
        return None, str(exc)


def load_user_directory(
    api_client: AdminApiClient,
    *,
    risk_status: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch the filtered A06 user-directory payload."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return None, "当前管理员会话不存在，请重新登录。"

    try:
        return api_client.list_users(
            access_token=access_token,
            risk_status=risk_status,
        ), None
    except AdminApiRequestError as exc:
        return None, normalize_admin_request_error(exc)
    except AdminApiClientError as exc:
        return None, str(exc)


def load_audit_log_snapshot(
    api_client: AdminApiClient,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch the filtered A07 audit-log payload using current widget state."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return None, "当前管理员会话不存在，请重新登录。"

    actor_type, actor_id = parse_actor_filter_key(
        str(st.session_state.get("admin_audit_actor_key") or "all")
    )
    action_code = str(st.session_state.get("admin_audit_action_code") or "all")
    target_type = str(st.session_state.get("admin_audit_target_type") or "all")
    date_from = st.session_state.get("admin_audit_date_from")
    date_to = st.session_state.get("admin_audit_date_to")

    try:
        return api_client.list_audit_logs(
            access_token=access_token,
            actor_type=actor_type,
            actor_id=actor_id,
            action_code=None if action_code == "all" else action_code,
            target_type=None if target_type == "all" else target_type,
            date_from=date_from.isoformat() if hasattr(date_from, "isoformat") else None,
            date_to=date_to.isoformat() if hasattr(date_to, "isoformat") else None,
        ), None
    except AdminApiRequestError as exc:
        return None, normalize_admin_request_error(exc)
    except AdminApiClientError as exc:
        return None, str(exc)


def handle_select_alert(
    api_client: AdminApiClient,
    *,
    alert_id: int,
) -> None:
    """Fetch and cache one explicit alert detail request to avoid repeat audit logs."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        set_admin_auth_error(st.session_state, "管理员会话不存在，请重新登录。")
        st.rerun()

    try:
        alert_detail = api_client.get_alert_detail(
            access_token=access_token,
            alert_id=alert_id,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"加载案例详情失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"加载案例详情失败：{exc}"},
        )
    else:
        preserved_detail = preserve_revealed_full_content(
            new_detail=alert_detail,
            existing_detail=get_selected_alert_detail(st.session_state),
        )
        set_selected_alert_detail(
            st.session_state,
            alert_id=alert_id,
            alert_detail=preserved_detail,
        )
    st.rerun()


def handle_select_post(
    api_client: AdminApiClient,
    *,
    post_id: int,
) -> None:
    """Fetch and cache one explicit post detail request for the A05 detail pane."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        set_admin_auth_error(st.session_state, "管理员会话不存在，请重新登录。")
        st.rerun()

    try:
        post_detail = api_client.get_post_detail(
            access_token=access_token,
            post_id=post_id,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"加载帖子详情失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"加载帖子详情失败：{exc}"},
        )
    else:
        preserved_detail = preserve_revealed_post_full_content(
            new_detail=post_detail,
            existing_detail=get_selected_post_detail(st.session_state),
        )
        set_selected_post_detail(
            st.session_state,
            post_id=post_id,
            post_detail=preserved_detail,
        )
    st.rerun()


def handle_select_user(
    api_client: AdminApiClient,
    *,
    student_id: int,
) -> None:
    """Fetch and cache one explicit user detail request for the A06 detail pane."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        set_admin_auth_error(st.session_state, "管理员会话不存在，请重新登录。")
        st.rerun()

    try:
        user_detail = api_client.get_user_detail(
            access_token=access_token,
            student_id=student_id,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"加载用户详情失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"加载用户详情失败：{exc}"},
        )
    else:
        preserved_detail = preserve_revealed_user_phone(
            new_detail=user_detail,
            existing_detail=get_selected_user_detail(st.session_state),
        )
        set_selected_user_detail(
            st.session_state,
            student_id=student_id,
            user_detail=preserved_detail,
        )
    st.rerun()


def handle_reveal_alert_content(
    api_client: AdminApiClient,
    *,
    alert_id: int,
) -> None:
    """Reveal the full treehole raw content for the selected alert case."""
    access_token = get_admin_access_token(st.session_state)
    current_detail = get_selected_alert_detail(st.session_state)
    if access_token is None or current_detail is None:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": "当前没有可用的管理员会话或案例详情。"},
        )
        st.rerun()

    try:
        content_payload = api_client.reveal_alert_content(
            access_token=access_token,
            alert_id=alert_id,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"展开完整原文失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"展开完整原文失败：{exc}"},
        )
    else:
        updated_detail = deepcopy(current_detail)
        updated_detail.setdefault("source", {})
        updated_detail["source"]["full_content"] = content_payload["full_content"]
        set_selected_alert_detail(
            st.session_state,
            alert_id=alert_id,
            alert_detail=updated_detail,
        )
        set_admin_alert_feedback(
            st.session_state,
            {"level": "success", "message": "已展开完整原文，并记录敏感查看审计。"},
        )
    st.rerun()


def handle_reveal_post_content(
    api_client: AdminApiClient,
    *,
    post_id: int,
) -> None:
    """Reveal the full treehole raw content for the selected managed post."""
    access_token = get_admin_access_token(st.session_state)
    current_detail = get_selected_post_detail(st.session_state)
    if access_token is None or current_detail is None:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": "当前没有可用的管理员会话或帖子详情。"},
        )
        st.rerun()

    try:
        content_payload = api_client.reveal_post_content(
            access_token=access_token,
            post_id=post_id,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"展开帖子原文失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"展开帖子原文失败：{exc}"},
        )
    else:
        updated_detail = deepcopy(current_detail)
        updated_detail.setdefault("content", {})
        updated_detail["content"]["full_content"] = content_payload["full_content"]
        set_selected_post_detail(
            st.session_state,
            post_id=post_id,
            post_detail=updated_detail,
        )
        set_admin_alert_feedback(
            st.session_state,
            {"level": "success", "message": "已展开完整原文，并记录敏感查看审计。"},
        )
    st.rerun()


def handle_reveal_user_phone(
    api_client: AdminApiClient,
    *,
    student_id: int,
) -> None:
    """Reveal the full phone number for the selected student detail."""
    access_token = get_admin_access_token(st.session_state)
    current_detail = get_selected_user_detail(st.session_state)
    if access_token is None or current_detail is None:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": "当前没有可用的管理员会话或用户详情。"},
        )
        st.rerun()

    try:
        payload = api_client.reveal_user_phone(
            access_token=access_token,
            student_id=student_id,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"展开完整手机号失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"展开完整手机号失败：{exc}"},
        )
    else:
        updated_detail = deepcopy(current_detail)
        updated_detail["full_phone"] = payload["full_phone"]
        set_selected_user_detail(
            st.session_state,
            student_id=student_id,
            user_detail=updated_detail,
        )
        set_admin_alert_feedback(
            st.session_state,
            {"level": "success", "message": "已展开完整手机号，并记录敏感查看审计。"},
        )
    st.rerun()


def handle_confirm_alert(
    api_client: AdminApiClient,
    *,
    alert_id: int,
    review_note: str,
    intervention_note: str,
) -> None:
    """Confirm one alert and refresh the selected detail cache."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        set_admin_auth_error(st.session_state, "管理员会话不存在，请重新登录。")
        st.rerun()

    try:
        api_client.confirm_alert(
            access_token=access_token,
            alert_id=alert_id,
            review_note=review_note,
            intervention_note=intervention_note,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"确认高风险失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"确认高风险失败：{exc}"},
        )
    else:
        refresh_selected_alert_detail(api_client, alert_id=alert_id)
        set_admin_alert_feedback(
            st.session_state,
            {"level": "success", "message": "已确认高风险，并写入模拟通知日志。"},
        )
    st.rerun()


def handle_dismiss_alert(
    api_client: AdminApiClient,
    *,
    alert_id: int,
    review_note: str,
) -> None:
    """Dismiss one alert as a false positive and refresh the detail cache."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        set_admin_auth_error(st.session_state, "管理员会话不存在，请重新登录。")
        st.rerun()

    try:
        api_client.dismiss_alert(
            access_token=access_token,
            alert_id=alert_id,
            review_note=review_note,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"标记误报失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"标记误报失败：{exc}"},
        )
    else:
        refresh_selected_alert_detail(api_client, alert_id=alert_id)
        set_admin_alert_feedback(
            st.session_state,
            {"level": "success", "message": "已标记误报，并更新案例状态。"},
        )
    st.rerun()


def handle_close_alert(
    api_client: AdminApiClient,
    *,
    alert_id: int,
    action_note: str,
) -> None:
    """Close one reviewed alert case and refresh the detail cache."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        set_admin_auth_error(st.session_state, "管理员会话不存在，请重新登录。")
        st.rerun()

    try:
        api_client.close_alert(
            access_token=access_token,
            alert_id=alert_id,
            action_note=action_note,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"结案失败：{normalize_admin_request_error(exc)}"},
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"结案失败：{exc}"},
        )
    else:
        refresh_selected_alert_detail(api_client, alert_id=alert_id)
        set_admin_alert_feedback(
            st.session_state,
            {"level": "success", "message": "案例已结案。"},
        )
    st.rerun()


def handle_add_alert_note(
    api_client: AdminApiClient,
    *,
    alert_id: int,
    action_note: str,
) -> None:
    """Append one intervention note and refresh the detail cache."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        set_admin_auth_error(st.session_state, "管理员会话不存在，请重新登录。")
        st.rerun()

    try:
        api_client.add_alert_note(
            access_token=access_token,
            alert_id=alert_id,
            action_note=action_note,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"写入干预记录失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"写入干预记录失败：{exc}"},
        )
    else:
        refresh_selected_alert_detail(api_client, alert_id=alert_id)
        set_admin_alert_feedback(
            st.session_state,
            {"level": "success", "message": "已追加干预记录。"},
        )
    st.rerun()


def handle_update_post_visibility(
    api_client: AdminApiClient,
    *,
    post_id: int,
    action: str,
) -> None:
    """Apply one admin post visibility action and refresh the selected post detail."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        set_admin_auth_error(st.session_state, "管理员会话不存在，请重新登录。")
        st.rerun()

    try:
        api_client.update_post_visibility(
            access_token=access_token,
            post_id=post_id,
            action=action,
        )
    except AdminApiRequestError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"{POST_VISIBILITY_ACTION_LABELS.get(action, action)}失败：{normalize_admin_request_error(exc)}",
            },
        )
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"{POST_VISIBILITY_ACTION_LABELS.get(action, action)}失败：{exc}",
            },
        )
    else:
        refresh_selected_post_detail(api_client, post_id=post_id)
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "success",
                "message": f"已执行：{POST_VISIBILITY_ACTION_LABELS.get(action, action)}。",
            },
        )
    st.rerun()


def refresh_selected_alert_detail(
    api_client: AdminApiClient,
    *,
    alert_id: int,
) -> None:
    """Refresh the selected alert detail after one explicit admin action."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return

    existing_detail = get_selected_alert_detail(st.session_state)
    try:
        refreshed_detail = api_client.get_alert_detail(
            access_token=access_token,
            alert_id=alert_id,
        )
    except AdminApiRequestError as exc:
        if exc.code == "ALERT_CASE_NOT_FOUND":
            clear_selected_alert_detail(st.session_state)
            set_admin_alert_feedback(
                st.session_state,
                {"level": "error", "message": "当前案例已不存在，已清除详情缓存。"},
            )
            return
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"刷新案例详情失败：{normalize_admin_request_error(exc)}",
            },
        )
        return
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"刷新案例详情失败：{exc}"},
        )
        return
    merged_detail = preserve_revealed_full_content(
        new_detail=refreshed_detail,
        existing_detail=existing_detail,
    )
    set_selected_alert_detail(
        st.session_state,
        alert_id=alert_id,
        alert_detail=merged_detail,
    )


def preserve_revealed_full_content(
    *,
    new_detail: dict[str, Any],
    existing_detail: dict[str, Any] | None,
) -> dict[str, Any]:
    """Carry over already revealed full content when the detail payload refreshes."""
    if existing_detail is None:
        return new_detail
    if int(existing_detail.get("alert_id", -1)) != int(new_detail.get("alert_id", -2)):
        return new_detail

    existing_source = existing_detail.get("source")
    if not isinstance(existing_source, dict):
        return new_detail
    full_content = existing_source.get("full_content")
    if not isinstance(full_content, str) or not full_content:
        return new_detail

    merged_detail = deepcopy(new_detail)
    merged_detail.setdefault("source", {})
    merged_detail["source"]["full_content"] = full_content
    return merged_detail


def refresh_selected_post_detail(
    api_client: AdminApiClient,
    *,
    post_id: int,
) -> None:
    """Refresh the selected post detail after one explicit admin action."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return

    existing_detail = get_selected_post_detail(st.session_state)
    try:
        refreshed_detail = api_client.get_post_detail(
            access_token=access_token,
            post_id=post_id,
        )
    except AdminApiRequestError as exc:
        if exc.code == "TREEHOLE_POST_NOT_FOUND":
            clear_selected_post_detail(st.session_state)
            set_admin_alert_feedback(
                st.session_state,
                {"level": "error", "message": "当前帖子已不存在，已清除详情缓存。"},
            )
            return
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"刷新帖子详情失败：{normalize_admin_request_error(exc)}",
            },
        )
        return
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"刷新帖子详情失败：{exc}"},
        )
        return

    merged_detail = preserve_revealed_post_full_content(
        new_detail=refreshed_detail,
        existing_detail=existing_detail,
    )
    set_selected_post_detail(
        st.session_state,
        post_id=post_id,
        post_detail=merged_detail,
    )


def refresh_selected_user_detail(
    api_client: AdminApiClient,
    *,
    student_id: int,
) -> None:
    """Refresh the selected user detail while preserving already revealed phone data."""
    access_token = get_admin_access_token(st.session_state)
    if access_token is None:
        return

    existing_detail = get_selected_user_detail(st.session_state)
    try:
        refreshed_detail = api_client.get_user_detail(
            access_token=access_token,
            student_id=student_id,
        )
    except AdminApiRequestError as exc:
        if exc.code == "STUDENT_NOT_FOUND":
            clear_selected_user_detail(st.session_state)
            set_admin_alert_feedback(
                st.session_state,
                {"level": "error", "message": "当前用户已不存在，已清除详情缓存。"},
            )
            return
        set_admin_alert_feedback(
            st.session_state,
            {
                "level": "error",
                "message": f"刷新用户详情失败：{normalize_admin_request_error(exc)}",
            },
        )
        return
    except AdminApiClientError as exc:
        set_admin_alert_feedback(
            st.session_state,
            {"level": "error", "message": f"刷新用户详情失败：{exc}"},
        )
        return

    merged_detail = preserve_revealed_user_phone(
        new_detail=refreshed_detail,
        existing_detail=existing_detail,
    )
    set_selected_user_detail(
        st.session_state,
        student_id=student_id,
        user_detail=merged_detail,
    )


def preserve_revealed_post_full_content(
    *,
    new_detail: dict[str, Any],
    existing_detail: dict[str, Any] | None,
) -> dict[str, Any]:
    """Carry over already revealed post raw content when the detail payload refreshes."""
    if existing_detail is None:
        return new_detail
    if int(existing_detail.get("post_id", -1)) != int(new_detail.get("post_id", -2)):
        return new_detail

    existing_content = existing_detail.get("content")
    if not isinstance(existing_content, dict):
        return new_detail
    full_content = existing_content.get("full_content")
    if not isinstance(full_content, str) or not full_content:
        return new_detail

    merged_detail = deepcopy(new_detail)
    merged_detail.setdefault("content", {})
    merged_detail["content"]["full_content"] = full_content
    return merged_detail


def preserve_revealed_user_phone(
    *,
    new_detail: dict[str, Any],
    existing_detail: dict[str, Any] | None,
) -> dict[str, Any]:
    """Carry over already revealed full phone data when the user detail refreshes."""
    if existing_detail is None:
        return new_detail
    if int(existing_detail.get("student_id", -1)) != int(new_detail.get("student_id", -2)):
        return new_detail

    full_phone = existing_detail.get("full_phone")
    if not isinstance(full_phone, str) or not full_phone:
        return new_detail

    merged_detail = deepcopy(new_detail)
    merged_detail["full_phone"] = full_phone
    return merged_detail


def build_actor_filter_key(actor_option: dict[str, Any]) -> str:
    """Return the stable selectbox key used for one A07 actor option."""
    actor_type = str(actor_option.get("actor_type") or "")
    actor_id = actor_option.get("actor_id")
    if actor_id is None:
        return actor_type
    return f"{actor_type}:{actor_id}"


def parse_actor_filter_key(actor_key: str) -> tuple[str | None, int | None]:
    """Parse one A07 actor selectbox key back into API filter params."""
    if actor_key == "all":
        return None, None
    if ":" not in actor_key:
        return actor_key, None
    actor_type, raw_actor_id = actor_key.split(":", maxsplit=1)
    try:
        return actor_type, int(raw_actor_id)
    except ValueError:
        return None, None


def normalize_admin_request_error(exc: AdminApiRequestError) -> str:
    """Handle auth-invalidating admin API failures and return a user-facing message."""
    if exc.status_code in {401, 403}:
        clear_admin_session(st.session_state)
        if exc.code == "ADMIN_ACCOUNT_INACTIVE" or exc.status_code == 403:
            set_admin_auth_error(st.session_state, "当前账户已被禁用，暂时无法访问后台。")
        else:
            set_admin_auth_error(st.session_state, "管理员会话已失效，请重新登录。")
        st.rerun()
    return exc.message


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


def render_analytics_summary_cards(analytics: dict[str, Any]) -> None:
    """Render the A08 overview cards above the chart grid."""
    summary_cards = build_analytics_summary_cards(analytics)
    st.caption("A08 统计概览")
    columns = st.columns(4)
    for column, (value, label, meta) in zip(columns, summary_cards, strict=True):
        with column:
            st.markdown(
                build_stat_card_html(value=value, label=label, meta=meta),
                unsafe_allow_html=True,
            )


def render_risk_distribution_chart(risk_distribution: dict[str, Any]) -> None:
    """Render the student risk-distribution chart and supporting raw table."""
    chart_rows = build_risk_distribution_chart_rows(risk_distribution)
    chart_spec = build_risk_distribution_chart_spec(chart_rows)
    chip_row = build_chip_row_html(
        [
            (
                f"{row['label']} {int(row['student_count'])}",
                str(row["tone"]),
            )
            for row in chart_rows
        ]
    )

    with st.container(border=True):
        st.markdown(
            build_chart_section_header_html(
                eyebrow="风险分布",
                title="学生风险档位分布",
                copy="按当前 `student_users.risk_status` 聚合，直接反映后台正在跟踪的整体风险结构。",
            ),
            unsafe_allow_html=True,
        )
        st.vega_lite_chart(chart_spec, use_container_width=True)
        st.markdown(chip_row, unsafe_allow_html=True)
        with st.expander("查看分布原始统计表"):
            st.dataframe(
                build_risk_distribution_table_rows(chart_rows),
                use_container_width=True,
                hide_index=True,
            )


def render_alert_processing_chart(alert_processing: dict[str, Any]) -> None:
    """Render the current alert queue-status distribution chart."""
    chart_rows = build_alert_processing_chart_rows(alert_processing)
    chart_spec = build_alert_processing_chart_spec(chart_rows)
    chip_row = build_chip_row_html(
        [
            (
                f"{row['label']} {int(row['case_count'])}",
                str(row["tone"]),
            )
            for row in chart_rows
        ]
    )

    with st.container(border=True):
        st.markdown(
            build_chart_section_header_html(
                eyebrow="工单状态",
                title="当前工单处理状态统计",
                copy="按 `queue_status` 聚合展示当前工单队列口径，可直接观察待复核、已确认、已忽略与已结案的结构。",
            ),
            unsafe_allow_html=True,
        )
        st.vega_lite_chart(chart_spec, use_container_width=True)
        st.markdown(chip_row, unsafe_allow_html=True)
        with st.expander("查看工单状态原始统计表"):
            st.dataframe(
                build_alert_processing_table_rows(chart_rows),
                use_container_width=True,
                hide_index=True,
            )


def render_daily_trend_chart(daily_trends: dict[str, Any]) -> None:
    """Render the fixed seven-day recent-activity trend chart."""
    chart_rows = build_daily_trend_chart_rows(daily_trends)
    chart_spec = build_daily_trend_chart_spec(chart_rows)
    table_rows = build_daily_trend_table_rows(daily_trends)
    totals = summarize_daily_trends(daily_trends)
    peak_summary = build_daily_trend_peak_summary(daily_trends)

    with st.container(border=True):
        st.markdown(
            build_chart_section_header_html(
                eyebrow="近 7 天趋势",
                title="后台活跃趋势",
                copy="固定观察最近 7 个自然日的问卷提交、树洞发帖与新建工单数量，帮助值班管理员快速识别波峰波谷。",
            ),
            unsafe_allow_html=True,
        )
        st.vega_lite_chart(chart_spec, use_container_width=True)
        summary_columns = st.columns(3)
        summary_columns[0].metric("7 天问卷提交", totals["questionnaire_submission_count"])
        summary_columns[1].metric("7 天树洞发帖", totals["treehole_post_count"])
        summary_columns[2].metric("7 天新建工单", totals["alert_case_count"])
        st.caption(
            f"活跃峰值日：{peak_summary['date_label']} · 总事件 {peak_summary['total_count']}。"
        )
        with st.expander("查看近 7 天原始统计表"):
            st.dataframe(
                table_rows,
                use_container_width=True,
                hide_index=True,
            )


def render_dashboard_unavailable_state() -> None:
    """Render the fallback state when one backend payload cannot be loaded."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">实时数据暂不可用</div>'
            '<p class="xinyu-empty-copy">'
            "JWT 会话仍已建立，但本次未能成功加载后端数据。你可以刷新重试。"
            "</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_queue_empty_state() -> None:
    """Render the empty queue state for one filtered alert status."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">当前筛选下没有案例</div>'
            '<p class="xinyu-empty-copy">'
            "可以切换其他状态筛选，或等待新的自动预警进入队列。"
            "</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_detail_empty_state() -> None:
    """Render the placeholder state before one alert case is explicitly opened."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">尚未打开案例详情</div>'
            '<p class="xinyu-empty-copy">'
            "请从左侧队列中选择一条案例。系统只会在你显式打开详情时写入敏感查看审计。"
            "</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_post_empty_state() -> None:
    """Render the empty list state for one filtered post status."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">当前筛选下没有帖子</div>'
            '<p class="xinyu-empty-copy">'
            "可以切换到其他帖子状态，或等待新的树洞内容进入后台管理范围。"
            "</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_post_detail_empty_state() -> None:
    """Render the placeholder state before one managed post is explicitly opened."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">尚未打开帖子详情</div>'
            '<p class="xinyu-empty-copy">'
            "请从左侧帖子列表中选择一条内容。完整原文只会在你显式展开时记录敏感查看审计。"
            "</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_user_empty_state() -> None:
    """Render the empty list state for one filtered user-directory view."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">当前筛选下没有用户</div>'
            '<p class="xinyu-empty-copy">'
            "可以切换风险状态筛选，或等待新的学生数据进入后台目录。"
            "</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_user_detail_empty_state() -> None:
    """Render the placeholder state before one student detail is explicitly opened."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">尚未打开用户详情</div>'
            '<p class="xinyu-empty-copy">'
            "请从左侧脱敏列表中选择一位学生。完整手机号只会在你显式展开时记录审计。"
            "</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_audit_empty_state() -> None:
    """Render the empty state when no audit logs match the current filters."""
    st.markdown(
        (
            '<div class="xinyu-empty-state">'
            '<div class="xinyu-empty-title">当前筛选下没有审计记录</div>'
            '<p class="xinyu-empty-copy">'
            "可以放宽操作者、动作类型或日期范围，查看其他敏感操作轨迹。"
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
    """Render the A02 module entry cards that point to current and future admin pages."""
    kpis = summary["kpis"]
    stats = summary["stats"]
    st.caption("模块入口")
    columns = (*st.columns(3), *st.columns(2))
    cards = (
        (
            "A03",
            "预警队列",
            "按优先级处理待复核案例，并进入 A04 详情完成人工复核。",
            f"待复核 {int(kpis.get('pending_review_count', 0))} · 最高优先级 {int(stats.get('highest_priority_pending_count', 0))}",
            "已实现",
        ),
        (
            "A05",
            "帖子管理",
            "查看已发布、被拦截、隐藏与软删除内容，并支持隐藏、保持隐藏与恢复发布。",
            f"已发布 {int(kpis.get('published_post_count', 0))} · 已拦截 {int(stats.get('blocked_post_count', 0))}",
            "已实现",
        ),
        (
            "A06",
            "用户目录",
            "按脱敏身份查看重点关注与高风险档案，并支持受控展开完整手机号。",
            f"重点关注 {int(kpis.get('focus_student_count', 0))} · 高风险档案 {int(stats.get('high_risk_student_count', 0))}",
            "已实现",
        ),
        (
            "A07",
            "审计日志",
            "按操作者、动作类型、目标对象和时间范围筛选敏感操作记录。",
            "管理员登录、敏感详情展开与人工处置都会写入审计。",
            "已实现",
        ),
        (
            "A08",
            "统计分析",
            "查看风险分布、近 7 天趋势和工单处理状态图，辅助日常值班判断整体运行态势。",
            f"高风险档案 {int(stats.get('high_risk_student_count', 0))} · 已确认高风险 {int(kpis.get('confirmed_high_risk_count', 0))}",
            "已实现",
        ),
    )
    for column, (step, title, copy, metric, status_label) in zip(columns, cards, strict=True):
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
        f'<div class="xinyu-kpi-label">{escape_html(label)}</div>'
        f'<div class="xinyu-kpi-meta">{escape_html(meta)}</div>'
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
        f'<div class="xinyu-stat-label">{escape_html(label)}</div>'
        f'<div class="xinyu-stat-meta">{escape_html(meta)}</div>'
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
        f'<span class="xinyu-nav-step">{escape_html(step)}</span>'
        f'<span class="xinyu-nav-status">{escape_html(status_label)}</span>'
        "</div>"
        f'<div class="xinyu-nav-title">{escape_html(title)}</div>'
        f'<div class="xinyu-nav-copy">{escape_html(copy)}</div>'
        f'<div class="xinyu-nav-metric">{escape_html(metric)}</div>'
        "</div>"
    )


def build_chart_section_header_html(
    *,
    eyebrow: str,
    title: str,
    copy: str,
) -> str:
    """Build one compact header block used at the top of each analytics chart card."""
    return (
        '<div class="xinyu-chart-header">'
        f'<div class="xinyu-chart-eyebrow">{escape_html(eyebrow)}</div>'
        f'<div class="xinyu-chart-title">{escape_html(title)}</div>'
        f'<div class="xinyu-chart-copy">{escape_html(copy)}</div>'
        "</div>"
    )


def build_chip_row_html(chips: list[tuple[str, str]]) -> str:
    """Build one horizontal chip row from label and tone pairs."""
    return (
        '<div class="xinyu-chip-row">'
        + "".join(build_chip_html(label, tone=tone) for label, tone in chips)
        + "</div>"
    )


def build_analytics_summary_cards(
    analytics: dict[str, Any],
) -> tuple[tuple[int, str, str], ...]:
    """Build the top-level A08 summary cards from the live analytics snapshot."""
    risk_distribution = analytics.get("risk_distribution") or {}
    daily_trends = analytics.get("daily_trends") or {}
    totals = summarize_daily_trends(daily_trends)
    date_window = (
        f"{str(daily_trends.get('start_date') or '--')} - {str(daily_trends.get('end_date') or '--')}"
    )
    return (
        (
            int(risk_distribution.get("total_students", 0)),
            "在册学生数",
            "按当前 `student_users.risk_status` 聚合",
        ),
        (
            totals["questionnaire_submission_count"],
            "7 天量表提交",
            f"窗口 {date_window}",
        ),
        (
            totals["treehole_post_count"],
            "7 天树洞发帖",
            "按 `treehole_posts.created_at` 统计",
        ),
        (
            totals["alert_case_count"],
            "7 天新建工单",
            "按 `alert_cases.created_at` 统计",
        ),
    )


def build_risk_distribution_chart_rows(
    risk_distribution: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize the risk-distribution payload into ordered chart rows."""
    items = risk_distribution.get("items") or []
    rows: list[dict[str, Any]] = []
    for item in items:
        risk_status = str(item.get("risk_status") or "normal")
        rows.append(
            {
                "risk_status": risk_status,
                "label": USER_RISK_LABELS.get(risk_status, risk_status),
                "student_count": int(item.get("student_count", 0)),
                "tone": USER_RISK_TONES.get(risk_status, "neutral"),
            }
        )
    return rows


def build_risk_distribution_table_rows(
    chart_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert chart rows into one raw table displayed under the risk chart."""
    return [
        {
            "风险状态": str(row["label"]),
            "学生人数": int(row["student_count"]),
        }
        for row in chart_rows
    ]


def build_risk_distribution_chart_spec(
    chart_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the Vega-Lite spec for the risk-distribution bar chart."""
    domain = [str(row["label"]) for row in chart_rows]
    colors = [
        {
            "success": "#3D9B5E",
            "warning": "#E5A23A",
            "danger": "#D84C4C",
            "neutral": "#70807C",
            "brand": "#2F8F83",
        }.get(str(row["tone"]), "#70807C")
        for row in chart_rows
    ]
    return {
        "data": {"values": chart_rows},
        "mark": {"type": "bar", "cornerRadiusEnd": 8},
        "height": 280,
        "encoding": {
            "y": {
                "field": "label",
                "type": "nominal",
                "sort": domain,
                "axis": {
                    "title": None,
                    "labelColor": "#41504C",
                    "labelFontSize": 12,
                    "labelFontWeight": 600,
                },
            },
            "x": {
                "field": "student_count",
                "type": "quantitative",
                "axis": {
                    "title": "学生人数",
                    "titleColor": "#70807C",
                    "labelColor": "#70807C",
                    "gridColor": "#EEF2F1",
                    "tickCount": 5,
                },
            },
            "color": {
                "field": "label",
                "type": "nominal",
                "scale": {"domain": domain, "range": colors},
                "legend": None,
            },
            "tooltip": [
                {"field": "label", "type": "nominal", "title": "风险状态"},
                {"field": "student_count", "type": "quantitative", "title": "学生人数"},
            ],
        },
        "config": {"view": {"stroke": None}},
    }


def build_alert_processing_chart_rows(
    alert_processing: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize the alert-processing payload into ordered chart rows."""
    items = alert_processing.get("items") or []
    rows: list[dict[str, Any]] = []
    for item in items:
        queue_status = str(item.get("queue_status") or "pending_review")
        rows.append(
            {
                "queue_status": queue_status,
                "label": ALERT_STATUS_LABELS.get(queue_status, queue_status),
                "case_count": int(item.get("case_count", 0)),
                "tone": resolve_status_tone(queue_status),
            }
        )
    return rows


def build_alert_processing_table_rows(
    chart_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert alert chart rows into one raw table displayed under the chart."""
    return [
        {
            "工单状态": str(row["label"]),
            "工单数量": int(row["case_count"]),
        }
        for row in chart_rows
    ]


def build_alert_processing_chart_spec(
    chart_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the Vega-Lite spec for the alert queue-status chart."""
    domain = [str(row["label"]) for row in chart_rows]
    colors = [
        {
            "warning": "#E5A23A",
            "danger": "#D84C4C",
            "neutral": "#70807C",
            "brand": "#2F8F83",
            "success": "#3D9B5E",
        }.get(str(row["tone"]), "#70807C")
        for row in chart_rows
    ]
    return {
        "data": {"values": chart_rows},
        "mark": {"type": "bar", "cornerRadiusTopLeft": 8, "cornerRadiusTopRight": 8},
        "height": 280,
        "encoding": {
            "x": {
                "field": "label",
                "type": "nominal",
                "sort": domain,
                "axis": {
                    "title": None,
                    "labelColor": "#41504C",
                    "labelFontSize": 12,
                    "labelFontWeight": 600,
                    "labelAngle": 0,
                },
            },
            "y": {
                "field": "case_count",
                "type": "quantitative",
                "axis": {
                    "title": "工单数量",
                    "titleColor": "#70807C",
                    "labelColor": "#70807C",
                    "gridColor": "#EEF2F1",
                    "tickCount": 5,
                },
            },
            "color": {
                "field": "label",
                "type": "nominal",
                "scale": {"domain": domain, "range": colors},
                "legend": None,
            },
            "tooltip": [
                {"field": "label", "type": "nominal", "title": "工单状态"},
                {"field": "case_count", "type": "quantitative", "title": "工单数量"},
            ],
        },
        "config": {"view": {"stroke": None}},
    }


def build_daily_trend_chart_rows(
    daily_trends: dict[str, Any],
) -> list[dict[str, Any]]:
    """Flatten the seven-day trend payload into long-form chart rows."""
    rows: list[dict[str, Any]] = []
    for item in daily_trends.get("items") or []:
        date_value = str(item.get("date") or "--")
        date_label = format_compact_date_label(date_value)
        for field_name, metric_label, _color in ANALYTICS_ACTIVITY_METRICS:
            rows.append(
                {
                    "date": date_value,
                    "date_label": date_label,
                    "metric_label": metric_label,
                    "count": int(item.get(field_name, 0)),
                }
            )
    return rows


def build_daily_trend_table_rows(
    daily_trends: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the raw seven-day trend table shown below the line chart."""
    return [
        {
            "日期": str(item.get("date") or "--"),
            "问卷提交": int(item.get("questionnaire_submission_count", 0)),
            "树洞发帖": int(item.get("treehole_post_count", 0)),
            "新建工单": int(item.get("alert_case_count", 0)),
        }
        for item in daily_trends.get("items") or []
    ]


def build_daily_trend_chart_spec(
    chart_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the Vega-Lite spec for the seven-day multi-series trend chart."""
    metric_domain = [label for _field, label, _color in ANALYTICS_ACTIVITY_METRICS]
    metric_colors = [color for _field, _label, color in ANALYTICS_ACTIVITY_METRICS]
    date_domain = list(dict.fromkeys(str(row["date_label"]) for row in chart_rows))
    return {
        "data": {"values": chart_rows},
        "mark": {
            "type": "line",
            "point": {"filled": True, "size": 72},
            "strokeWidth": 3,
        },
        "height": 320,
        "encoding": {
            "x": {
                "field": "date_label",
                "type": "ordinal",
                "sort": date_domain,
                "axis": {
                    "title": None,
                    "labelColor": "#41504C",
                    "labelFontSize": 12,
                    "labelAngle": 0,
                },
            },
            "y": {
                "field": "count",
                "type": "quantitative",
                "axis": {
                    "title": "数量",
                    "titleColor": "#70807C",
                    "labelColor": "#70807C",
                    "gridColor": "#EEF2F1",
                    "tickCount": 6,
                },
            },
            "color": {
                "field": "metric_label",
                "type": "nominal",
                "scale": {"domain": metric_domain, "range": metric_colors},
                "legend": {
                    "title": None,
                    "labelColor": "#41504C",
                    "orient": "top",
                },
            },
            "tooltip": [
                {"field": "date", "type": "nominal", "title": "日期"},
                {"field": "metric_label", "type": "nominal", "title": "指标"},
                {"field": "count", "type": "quantitative", "title": "数量"},
            ],
        },
        "config": {"view": {"stroke": None}},
    }


def summarize_daily_trends(daily_trends: dict[str, Any]) -> dict[str, int]:
    """Aggregate seven-day totals for the A08 headline summary and metrics."""
    totals = {
        "questionnaire_submission_count": 0,
        "treehole_post_count": 0,
        "alert_case_count": 0,
    }
    for item in daily_trends.get("items") or []:
        for field_name in totals:
            totals[field_name] += int(item.get(field_name, 0))
    return totals


def build_daily_trend_peak_summary(daily_trends: dict[str, Any]) -> dict[str, Any]:
    """Return the highest-activity day within the current seven-day window."""
    best_date = "--"
    best_total = 0
    for item in daily_trends.get("items") or []:
        total = (
            int(item.get("questionnaire_submission_count", 0))
            + int(item.get("treehole_post_count", 0))
            + int(item.get("alert_case_count", 0))
        )
        if total > best_total:
            best_total = total
            best_date = format_compact_date_label(str(item.get("date") or "--"))
    return {"date_label": best_date, "total_count": best_total}


def format_compact_date_label(raw_value: str) -> str:
    """Format one ISO date string into a compact month-day label."""
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return raw_value
    return parsed.strftime("%m-%d")


def build_alert_queue_card_html(
    alert_item: dict[str, Any],
    *,
    is_active: bool,
) -> str:
    """Build one left-panel alert queue card."""
    queue_status = str(alert_item.get("queue_status") or "--")
    review_priority = str(alert_item.get("review_priority") or "--")
    risk_status = str(alert_item.get("risk_status") or "--")
    return (
        f'<div class="xinyu-alert-card{" xinyu-alert-card-active" if is_active else ""}">'
        '<div class="xinyu-alert-card-header">'
        f'<div class="xinyu-alert-card-title">#{int(alert_item.get("alert_id", 0))} · {escape_html(str(alert_item.get("source_label") or "--"))}</div>'
        f'<div class="xinyu-alert-card-meta">{escape_html(format_dashboard_timestamp(alert_item.get("created_at")))} · {escape_html(str(alert_item.get("student_label") or "--"))}</div>'
        "</div>"
        '<div class="xinyu-chip-row">'
        f'{build_chip_html(PRIORITY_LABELS.get(review_priority, review_priority), tone=resolve_priority_tone(review_priority))}'
        f'{build_chip_html(ALERT_STATUS_LABELS.get(queue_status, queue_status), tone=resolve_status_tone(queue_status))}'
        f'{build_chip_html(render_risk_label(risk_status), tone=RISK_TONES.get(risk_status, "neutral"))}'
        "</div>"
        f'<div class="xinyu-alert-card-copy">{escape_html(str(alert_item.get("source_preview") or "--"))}</div>'
        f'<div class="xinyu-alert-card-foot">手机号：{escape_html(str(alert_item.get("masked_phone") or "--"))} · {escape_html(str(alert_item.get("college_name") or "--"))} / {escape_html(str(alert_item.get("class_name") or "--"))}</div>'
        "</div>"
    )


def build_post_queue_card_html(
    post_item: dict[str, Any],
    *,
    is_active: bool,
) -> str:
    """Build one left-panel A05 post-management card."""
    publish_status = str(post_item.get("publish_status") or "--")
    risk_level = str(post_item.get("risk_level") or "--")
    timing = (
        post_item.get("published_at")
        or post_item.get("deleted_at")
        or post_item.get("created_at")
    )
    return (
        f'<div class="xinyu-alert-card{" xinyu-alert-card-active" if is_active else ""}">'
        '<div class="xinyu-alert-card-header">'
        f'<div class="xinyu-alert-card-title">#{int(post_item.get("post_id", 0))} · {escape_html(str(post_item.get("anonymous_name") or "--"))}</div>'
        f'<div class="xinyu-alert-card-meta">{escape_html(format_dashboard_timestamp(timing))} · {escape_html(str(post_item.get("student_label") or "--"))}</div>'
        "</div>"
        '<div class="xinyu-chip-row">'
        f'{build_chip_html(POST_STATUS_LABELS.get(publish_status, publish_status), tone=resolve_post_status_tone(publish_status))}'
        f'{build_chip_html(render_risk_label(risk_level), tone=RISK_TONES.get(risk_level, "neutral"))}'
        f'{build_chip_html("互动 " + str(int(post_item.get("total_reaction_count", 0))), tone="brand")}'
        "</div>"
        f'<div class="xinyu-alert-card-copy">{escape_html(str(post_item.get("source_preview") or "--"))}</div>'
        f'<div class="xinyu-alert-card-foot">手机号：{escape_html(str(post_item.get("masked_phone") or "--"))} · {escape_html(str(post_item.get("college_name") or "--"))} / {escape_html(str(post_item.get("class_name") or "--"))}</div>'
        "</div>"
    )


def build_user_directory_card_html(
    user_item: dict[str, Any],
    *,
    is_active: bool,
) -> str:
    """Build one left-panel A06 user-directory card."""
    risk_status = str(user_item.get("risk_status") or "--")
    consent_status = str(user_item.get("consent_status") or "--")
    return (
        f'<div class="xinyu-alert-card{" xinyu-alert-card-active" if is_active else ""}">'
        '<div class="xinyu-alert-card-header">'
        f'<div class="xinyu-alert-card-title">{escape_html(str(user_item.get("student_label") or "--"))}</div>'
        f'<div class="xinyu-alert-card-meta">{escape_html(format_dashboard_timestamp(user_item.get("updated_at")))} · 最近登录 {escape_html(format_dashboard_timestamp(user_item.get("last_login_at")))}</div>'
        "</div>"
        '<div class="xinyu-chip-row">'
        f'{build_chip_html(render_risk_label(risk_status), tone=RISK_TONES.get(risk_status, "neutral"))}'
        f'{build_chip_html("关注 " + str(int(user_item.get("active_focus_count", 0))), tone="warning")}'
        f'{build_chip_html("工单 " + str(int(user_item.get("open_alert_count", 0))), tone="danger" if int(user_item.get("open_alert_count", 0)) else "brand")}'
        f'{build_chip_html(consent_status, tone="neutral")}'
        "</div>"
        f'<div class="xinyu-alert-card-copy">{escape_html(str(user_item.get("masked_phone") or "--"))} · {escape_html(str(user_item.get("college_name") or "--"))} / {escape_html(str(user_item.get("class_name") or "--"))}</div>'
        "</div>"
    )


def build_alert_detail_header_html(alert_detail: dict[str, Any]) -> str:
    """Build the A04 detail header card."""
    return (
        '<div class="xinyu-detail-card">'
        f'<div class="xinyu-detail-title">案例 #{int(alert_detail.get("alert_id", 0))} · {escape_html(str(alert_detail.get("source_type_label") or "--"))}</div>'
        f'<div class="xinyu-detail-copy">{escape_html(str(alert_detail.get("ai_reason_text") or "暂无系统说明。"))}</div>'
        '<div class="xinyu-chip-row">'
        f'{build_chip_html(str(alert_detail.get("review_priority_label") or "--"), tone=resolve_priority_tone(str(alert_detail.get("review_priority") or "")))}'
        f'{build_chip_html(str(alert_detail.get("queue_status_label") or "--"), tone=resolve_status_tone(str(alert_detail.get("queue_status") or "")))}'
        f'{build_chip_html(str(alert_detail.get("source_type_label") or "--"), tone="brand")}'
        "</div>"
        f'<div class="xinyu-detail-foot">创建时间：{escape_html(format_dashboard_timestamp(alert_detail.get("created_at")))}'
        f' · 最近复核：{escape_html(format_dashboard_timestamp(alert_detail.get("reviewed_at")))}'
        "</div>"
        "</div>"
    )


def build_post_detail_header_html(post_detail: dict[str, Any]) -> str:
    """Build the A05 detail header card."""
    publish_status = str(post_detail.get("publish_status") or "--")
    risk_level = str(post_detail.get("risk_level") or "--")
    return (
        '<div class="xinyu-detail-card">'
        f'<div class="xinyu-detail-title">帖子 #{int(post_detail.get("post_id", 0))} · {escape_html(str(post_detail.get("anonymous_name") or "--"))}</div>'
        f'<div class="xinyu-chip-row">'
        f'{build_chip_html(POST_STATUS_LABELS.get(publish_status, publish_status), tone=resolve_post_status_tone(publish_status))}'
        f'{build_chip_html(render_risk_label(risk_level), tone=RISK_TONES.get(risk_level, "neutral"))}'
        f'{build_chip_html("公开可见" if post_detail.get("allow_publication") else "当前非公开", tone="brand")}'
        "</div>"
        f'<div class="xinyu-detail-foot">创建时间：{escape_html(format_dashboard_timestamp(post_detail.get("created_at")))}'
        f' · 发布时间：{escape_html(format_dashboard_timestamp(post_detail.get("published_at")))}'
        f' · 删除时间：{escape_html(format_dashboard_timestamp(post_detail.get("deleted_at")))}'
        "</div>"
        "</div>"
    )


def build_user_detail_header_html(user_detail: dict[str, Any]) -> str:
    """Build the A06 detail header card."""
    risk_status = str(user_detail.get("risk_status") or "--")
    consent_status = str(user_detail.get("consent_status") or "--")
    return (
        '<div class="xinyu-detail-card">'
        f'<div class="xinyu-detail-title">{escape_html(str(user_detail.get("student_label") or "--"))}</div>'
        '<div class="xinyu-chip-row">'
        f'{build_chip_html(render_risk_label(risk_status), tone=RISK_TONES.get(risk_status, "neutral"))}'
        f'{build_chip_html("授权 " + consent_status, tone="brand")}'
        f'{build_chip_html("演示账号" if user_detail.get("is_demo") else "正式账号", tone="neutral")}'
        "</div>"
        f'<div class="xinyu-detail-foot">创建时间：{escape_html(format_dashboard_timestamp(user_detail.get("created_at")))}'
        f' · 最近更新：{escape_html(format_dashboard_timestamp(user_detail.get("updated_at")))}'
        "</div>"
        "</div>"
    )


def build_copy_block_html(
    *,
    title: str,
    body: str,
    tone: str,
) -> str:
    """Build one copy-focused content block with semantic tone."""
    body_html = escape_html(body).replace("\n", "<br/>")
    return (
        f'<div class="xinyu-copy-block xinyu-copy-block-{tone}">'
        f'<div class="xinyu-copy-block-title">{escape_html(title)}</div>'
        f'<div class="xinyu-copy-block-body">{body_html}</div>'
        "</div>"
    )


def build_ai_analysis_card_html(ai_analysis: dict[str, Any]) -> str:
    """Build one AI analysis summary card for treehole alert details."""
    trigger_phrases = "、".join(str(item) for item in ai_analysis.get("trigger_phrases", [])) or "无"
    emotion_tags = "、".join(str(item) for item in ai_analysis.get("emotion_tags", [])) or "无"
    return (
        '<div class="xinyu-detail-card">'
        '<div class="xinyu-detail-title">AI 分析结果</div>'
        f'<div class="xinyu-detail-copy">风险等级：{escape_html(render_risk_label(str(ai_analysis.get("parsed_risk_level") or "--")))}'
        f' · 风险分：{escape_html(str(ai_analysis.get("parsed_risk_score") or "--"))}'
        f' · 回退：{escape_html("是" if ai_analysis.get("fallback_used") else "否")}</div>'
        f'<div class="xinyu-detail-foot">触发短语：{escape_html(trigger_phrases)} · 情绪标签：{escape_html(emotion_tags)}</div>'
        f'<div class="xinyu-alert-card-copy">{escape_html(str(ai_analysis.get("reason_text") or "--"))}</div>'
        "</div>"
    )


def build_user_questionnaire_item_html(item: dict[str, Any]) -> str:
    """Build one latest-questionnaire card for the A06 risk archive."""
    questionnaire_code = str(item.get("questionnaire_code") or "--")
    questionnaire_name = str(item.get("questionnaire_name") or questionnaire_code)
    risk_level = str(item.get("risk_level") or "--")
    score_bits = [f"原始分 {item.get('raw_score', '--')}"]
    if item.get("standardized_score") is not None:
        score_bits.append(f"标准分 {item.get('standardized_score')}")
    if item.get("hard_trigger_hit"):
        score_bits.append("命中硬触发")
    return (
        '<div class="xinyu-history-card">'
        f'<div class="xinyu-history-title">{escape_html(questionnaire_code)} · {escape_html(questionnaire_name)}</div>'
        f'<div class="xinyu-chip-row">{build_chip_html(render_risk_label(risk_level), tone=RISK_TONES.get(risk_level, "neutral"))}</div>'
        f'<div class="xinyu-history-copy">{escape_html("，".join(score_bits))}</div>'
        f'<div class="xinyu-history-foot">{escape_html(format_dashboard_timestamp(item.get("submitted_at")))}</div>'
        "</div>"
    )


def build_user_post_item_html(item: dict[str, Any]) -> str:
    """Build one recent-treehole-post card for the A06 risk archive."""
    publish_status = str(item.get("publish_status") or "--")
    risk_level = str(item.get("risk_level") or "--")
    return (
        '<div class="xinyu-history-card">'
        f'<div class="xinyu-history-title">帖子 #{int(item.get("post_id", 0))}</div>'
        '<div class="xinyu-chip-row">'
        f'{build_chip_html(POST_STATUS_LABELS.get(publish_status, publish_status), tone=resolve_post_status_tone(publish_status))}'
        f'{build_chip_html(render_risk_label(risk_level), tone=RISK_TONES.get(risk_level, "neutral"))}'
        "</div>"
        f'<div class="xinyu-history-foot">创建时间：{escape_html(format_dashboard_timestamp(item.get("created_at")))} · 发布时间：{escape_html(format_dashboard_timestamp(item.get("published_at")))}</div>'
        "</div>"
    )


def build_focus_entry_card_html(item: dict[str, Any]) -> str:
    """Build one focus-entry summary card for the A06 detail pane."""
    return (
        '<div class="xinyu-timeline-item">'
        f'<div class="xinyu-timeline-title">{escape_html(str(item.get("reason_code") or "--"))}</div>'
        f'<div class="xinyu-timeline-copy">状态：{escape_html(str(item.get("status") or "--"))}</div>'
        f'<div class="xinyu-timeline-foot">{escape_html(format_dashboard_timestamp(item.get("created_at")))}</div>'
        "</div>"
    )


def build_recent_alert_summary_html(item: dict[str, Any]) -> str:
    """Build one recent alert-case summary card for the A06 detail pane."""
    queue_status = str(item.get("queue_status") or "--")
    review_priority = str(item.get("review_priority") or "--")
    return (
        '<div class="xinyu-timeline-item">'
        f'<div class="xinyu-timeline-title">案例 #{int(item.get("alert_id", 0))}</div>'
        '<div class="xinyu-chip-row">'
        f'{build_chip_html(ALERT_STATUS_LABELS.get(queue_status, queue_status), tone=resolve_status_tone(queue_status))}'
        f'{build_chip_html(PRIORITY_LABELS.get(review_priority, review_priority), tone=resolve_priority_tone(review_priority))}'
        f'{build_chip_html(str(item.get("source_type") or "--"), tone="brand")}'
        "</div>"
        f'<div class="xinyu-timeline-foot">{escape_html(format_dashboard_timestamp(item.get("created_at")))}</div>'
        "</div>"
    )


def build_history_item_card_html(item: dict[str, Any]) -> str:
    """Build one latest-questionnaire history card."""
    questionnaire_code = str(item.get("questionnaire_code") or "--")
    questionnaire_name = str(item.get("questionnaire_name") or questionnaire_code)
    risk_level = str(item.get("risk_level") or "--")
    score_bits = [f"原始分 {item.get('raw_score', '--')}"]
    if item.get("standardized_score") is not None:
        score_bits.append(f"标准分 {item.get('standardized_score')}")
    if item.get("hard_trigger_hit"):
        score_bits.append("命中硬触发")
    if item.get("is_current_source"):
        score_bits.append("当前来源")
    return (
        '<div class="xinyu-history-card">'
        f'<div class="xinyu-history-title">{escape_html(questionnaire_code)} · {escape_html(questionnaire_name)}</div>'
        f'<div class="xinyu-chip-row">{build_chip_html(render_risk_label(risk_level), tone=RISK_TONES.get(risk_level, "neutral"))}</div>'
        f'<div class="xinyu-history-copy">{escape_html("，".join(score_bits))}</div>'
        f'<div class="xinyu-history-foot">{escape_html(format_dashboard_timestamp(item.get("submitted_at")))}</div>'
        "</div>"
    )


def build_timeline_item_html(item: dict[str, Any]) -> str:
    """Build one intervention timeline card."""
    action_type = str(item.get("action_type") or "--")
    action_label = INTERVENTION_ACTION_LABELS.get(action_type, action_type)
    note = str(item.get("action_note") or "未填写说明。")
    admin_display_name = str(item.get("admin_display_name") or "--")
    role_code = str(item.get("admin_role_code") or "--")
    return (
        '<div class="xinyu-timeline-item">'
        f'<div class="xinyu-timeline-title">{escape_html(action_label)}</div>'
        f'<div class="xinyu-timeline-copy">{escape_html(note)}</div>'
        f'<div class="xinyu-timeline-foot">{escape_html(format_dashboard_timestamp(item.get("created_at")))}'
        f' · {escape_html(admin_display_name)} / {escape_html(role_code)}</div>'
        "</div>"
    )


def build_audit_record_card_html(record: dict[str, Any]) -> str:
    """Build one audit-record card for the A07 page."""
    action_code = str(record.get("action_code") or "--")
    target_type = str(record.get("target_type") or "--")
    actor_type = str(record.get("actor_type") or "--")
    summary_text = str(record.get("summary_text") or "--")
    metadata_json = record.get("metadata_json")
    metadata_summary = ""
    if isinstance(metadata_json, dict) and metadata_json:
        metadata_summary = " · ".join(
            f"{key}={value}" for key, value in metadata_json.items()
        )
    footer_bits = [
        format_dashboard_timestamp(record.get("created_at")),
        str(record.get("ip_address") or "无 IP"),
    ]
    if metadata_summary:
        footer_bits.append(metadata_summary)
    return (
        '<div class="xinyu-timeline-item">'
        f'<div class="xinyu-timeline-title">{escape_html(str(record.get("actor_label") or "--"))} · {escape_html(action_code)}</div>'
        '<div class="xinyu-chip-row">'
        f'{build_chip_html(AUDIT_ACTOR_TYPE_LABELS.get(actor_type, actor_type), tone="brand")}'
        f'{build_chip_html(target_type, tone="neutral")}'
        f'{build_chip_html(str(record.get("target_label") or "--"), tone="warning")}'
        "</div>"
        f'<div class="xinyu-timeline-copy">{escape_html(summary_text)}</div>'
        f'<div class="xinyu-timeline-foot">{escape_html(" · ".join(footer_bits))}</div>'
        "</div>"
    )


def build_chip_html(label: str, *, tone: str) -> str:
    """Build one small semantic chip."""
    return f'<span class="xinyu-chip xinyu-chip-{escape_html(tone)}">{escape_html(label)}</span>'


def resolve_status_tone(queue_status: str) -> str:
    """Map queue statuses onto alert-chip tones."""
    return {
        "pending_review": "warning",
        "confirmed_pending_intervention": "danger",
        "dismissed_false_positive": "neutral",
        "closed": "brand",
    }.get(queue_status, "neutral")


def resolve_post_status_tone(publish_status: str) -> str:
    """Map post publication statuses onto management-chip tones."""
    return {
        "published": "success",
        "hidden_by_admin": "warning",
        "blocked_high_risk": "danger",
        "deleted_by_user": "neutral",
    }.get(publish_status, "neutral")


def resolve_priority_tone(review_priority: str) -> str:
    """Map review priorities onto alert-chip tones."""
    return {
        "highest": "danger",
        "urgent": "warning",
        "normal": "brand",
    }.get(review_priority, "neutral")


def render_risk_label(risk_level: str) -> str:
    """Return the localized risk label used across A02-A04."""
    return RISK_LABELS.get(risk_level, risk_level)


def format_dashboard_timestamp(raw_value: Any) -> str:
    """Format timestamps returned by the backend for console display."""
    if isinstance(raw_value, datetime):
        return raw_value.strftime("%Y-%m-%d %H:%M:%S")
    if not isinstance(raw_value, str) or not raw_value:
        return "--"

    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return raw_value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def escape_html(value: str) -> str:
    """Escape one string before interpolating it into inline HTML snippets."""
    return html.escape(value, quote=True)


if __name__ == "__main__":
    main()
