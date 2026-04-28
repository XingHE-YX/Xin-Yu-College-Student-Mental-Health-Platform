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
    get_admin_access_token,
    get_admin_active_view,
    get_admin_auth_error,
    get_admin_profile,
    get_selected_alert_detail,
    get_selected_alert_id,
    get_selected_post_detail,
    get_selected_post_id,
    is_admin_authenticated,
    pop_admin_alert_feedback,
    set_admin_active_view,
    set_admin_alert_feedback,
    set_admin_auth_error,
    set_admin_session,
    set_selected_alert_detail,
    set_selected_post_detail,
)
from admin.utils.config import get_admin_api_base_url
from admin.utils.styles import build_admin_console_css

VIEW_DASHBOARD = "dashboard"
VIEW_ALERTS = "alerts"
VIEW_POSTS = "posts"
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
        button_columns = st.columns(4)
        with button_columns[0]:
            if st.button("进入 A03", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_ALERTS)
                st.rerun()
        with button_columns[1]:
            if st.button("进入 A05", use_container_width=True):
                set_admin_active_view(st.session_state, VIEW_POSTS)
                st.rerun()
        with button_columns[2]:
            if st.button("刷新总览", use_container_width=True):
                st.rerun()
        with button_columns[3]:
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
    top_row = st.columns(2)
    bottom_row = st.columns(2)
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
            "按脱敏身份查看重点关注与高风险档案，后续支持敏感信息受控展开。",
            f"重点关注 {int(kpis.get('focus_student_count', 0))} · 高风险档案 {int(stats.get('high_risk_student_count', 0))}",
            "11.5 后续",
        ),
        (
            "A07",
            "审计日志",
            "跟踪后台敏感查看、人工复核和模拟通知等关键操作。",
            "管理员登录、敏感详情展开与人工处置都会写入审计。",
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
        f'{build_chip_html(f"互动 {int(post_item.get("total_reaction_count", 0))}", tone="brand")}'
        "</div>"
        f'<div class="xinyu-alert-card-copy">{escape_html(str(post_item.get("source_preview") or "--"))}</div>'
        f'<div class="xinyu-alert-card-foot">手机号：{escape_html(str(post_item.get("masked_phone") or "--"))} · {escape_html(str(post_item.get("college_name") or "--"))} / {escape_html(str(post_item.get("class_name") or "--"))}</div>'
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
