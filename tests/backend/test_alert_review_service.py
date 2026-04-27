"""Tests for manual alert review actions and intervention logging."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.constants.account_enums import AdminRoleCode
from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    AuditActorType,
    CaseSourceType,
    InterventionActionType,
    ReviewPriority,
)
from src.models import AdminUser, AlertCase, AuditLog, Base, InterventionLog, StudentUser
from src.services.alert_review_service import (
    AlertReviewService,
    InvalidAlertCaseTransitionError,
)


def create_review_service_session() -> tuple[Session, AlertCase, AdminUser]:
    """Create one isolated session with a pending alert case and one active admin."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)

    student = StudentUser(
        phone_e164="+8613812345609",
        wechat_openid="wx-alert-review-001",
        display_nickname="复核同学",
        display_avatar_seed="seed-alert-review",
        college_name="心理学院",
        class_name="2026级1班",
    )
    admin = AdminUser(
        username="platform.admin",
        password_hash="argon2$review",
        role_code=AdminRoleCode.PLATFORM_ADMIN,
        display_name="平台管理员",
    )
    session.add_all([student, admin])
    session.flush()

    alert_case = AlertCase(
        student_id=student.id,
        source_type=CaseSourceType.TREEHOLE,
        case_level=AlertCaseLevel.HIGH,
        queue_status=AlertQueueStatus.PENDING_REVIEW,
        review_priority=ReviewPriority.HIGHEST,
        ai_reason_text="检测到明确高风险信号。",
    )
    session.add(alert_case)
    session.commit()
    session.refresh(alert_case)
    session.refresh(admin)
    return session, alert_case, admin


def list_intervention_logs(session: Session, alert_case_id: int) -> list[InterventionLog]:
    """Return intervention logs for one alert case in creation order."""
    statement = (
        select(InterventionLog)
        .where(InterventionLog.alert_case_id == alert_case_id)
        .order_by(InterventionLog.id)
    )
    return list(session.scalars(statement).all())


def list_audit_logs(session: Session, alert_case_id: int) -> list[AuditLog]:
    """Return audit logs for one alert case in creation order."""
    statement = (
        select(AuditLog)
        .where(AuditLog.target_type == "alert_case", AuditLog.target_id == alert_case_id)
        .order_by(AuditLog.id)
    )
    return list(session.scalars(statement).all())


def test_confirm_high_risk_updates_case_and_writes_intervention_and_audit_logs() -> None:
    """Confirm should move the case forward and persist both review and contact logs."""
    session, alert_case, admin = create_review_service_session()

    result = AlertReviewService(session).confirm_high_risk(
        alert_case_id=alert_case.id,
        admin_user_id=admin.id,
        review_note="人工复核确认存在明确自伤风险。",
        intervention_note="已登记模拟联系辅导员和值班老师。",
        ip_address="127.0.0.1",
    )

    refreshed_case = session.get(AlertCase, result.alert_case.id)
    assert refreshed_case is not None
    assert refreshed_case.queue_status is AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION
    assert refreshed_case.review_note == "人工复核确认存在明确自伤风险。"
    assert refreshed_case.reviewed_by == admin.id
    assert refreshed_case.reviewed_at is not None
    assert refreshed_case.simulated_notice_log is not None
    assert refreshed_case.simulated_notice_log.startswith("[SIMULATED]")
    assert "模拟联系辅导员" in refreshed_case.simulated_notice_log

    intervention_logs = list_intervention_logs(session, refreshed_case.id)
    assert [log.action_type for log in intervention_logs] == [
        InterventionActionType.CONFIRM_HIGH_RISK,
        InterventionActionType.SIMULATE_CONTACT,
    ]
    assert intervention_logs[0].action_note == "人工复核确认存在明确自伤风险。"
    assert intervention_logs[1].action_note == "已登记模拟联系辅导员和值班老师。"

    audit_logs = list_audit_logs(session, refreshed_case.id)
    assert [log.action_code for log in audit_logs] == [
        "ADMIN_CONFIRM_ALERT_CASE",
        "SYSTEM_CREATE_SIMULATED_NOTICE_LOG",
    ]
    assert [log.actor_type for log in audit_logs] == [
        AuditActorType.ADMIN,
        AuditActorType.SYSTEM,
    ]
    assert audit_logs[0].actor_id == admin.id
    assert audit_logs[0].ip_address == "127.0.0.1"
    assert audit_logs[1].actor_id is None
    assert audit_logs[1].metadata_json is not None
    assert audit_logs[1].metadata_json["admin_user_id"] == admin.id

    session.close()


def test_dismiss_false_positive_updates_case_and_writes_one_log() -> None:
    """Dismiss should mark the case as false positive and append one review log."""
    session, alert_case, admin = create_review_service_session()

    result = AlertReviewService(session).dismiss_false_positive(
        alert_case_id=alert_case.id,
        admin_user_id=admin.id,
        review_note="复核后判断为情绪宣泄，不构成真实危机。",
    )

    refreshed_case = session.get(AlertCase, result.alert_case.id)
    assert refreshed_case is not None
    assert refreshed_case.queue_status is AlertQueueStatus.DISMISSED_FALSE_POSITIVE
    assert refreshed_case.review_note == "复核后判断为情绪宣泄，不构成真实危机。"
    assert refreshed_case.reviewed_by == admin.id
    assert refreshed_case.reviewed_at is not None
    assert refreshed_case.simulated_notice_log is None

    intervention_logs = list_intervention_logs(session, refreshed_case.id)
    assert len(intervention_logs) == 1
    assert intervention_logs[0].action_type is InterventionActionType.DISMISS_FALSE_POSITIVE

    audit_logs = list_audit_logs(session, refreshed_case.id)
    assert len(audit_logs) == 1
    assert audit_logs[0].action_code == "ADMIN_DISMISS_ALERT_CASE"
    assert audit_logs[0].actor_type is AuditActorType.ADMIN

    session.close()


def test_close_case_from_confirmed_state_writes_closure_log() -> None:
    """Close should only finalize a reviewed case and preserve earlier review metadata."""
    session, alert_case, admin = create_review_service_session()
    service = AlertReviewService(session)
    service.confirm_high_risk(
        alert_case_id=alert_case.id,
        admin_user_id=admin.id,
        review_note="需要进一步跟进。",
        intervention_note="已登记模拟联系。",
    )

    result = service.close_case(
        alert_case_id=alert_case.id,
        admin_user_id=admin.id,
        action_note="处置记录已归档，工单结案。",
    )

    refreshed_case = session.get(AlertCase, result.alert_case.id)
    assert refreshed_case is not None
    assert refreshed_case.queue_status is AlertQueueStatus.CLOSED
    assert refreshed_case.review_note == "需要进一步跟进。"
    assert refreshed_case.reviewed_by == admin.id

    intervention_logs = list_intervention_logs(session, refreshed_case.id)
    assert intervention_logs[-1].action_type is InterventionActionType.CLOSE_CASE
    assert intervention_logs[-1].action_note == "处置记录已归档，工单结案。"

    audit_logs = list_audit_logs(session, refreshed_case.id)
    assert audit_logs[-1].action_code == "ADMIN_CLOSE_ALERT_CASE"

    session.close()


def test_add_intervention_note_does_not_change_queue_status() -> None:
    """Add-note should append a timeline item while keeping the case status unchanged."""
    session, alert_case, admin = create_review_service_session()

    result = AlertReviewService(session).add_intervention_note(
        alert_case_id=alert_case.id,
        admin_user_id=admin.id,
        action_note="补充说明：已联系班主任核对近况。",
    )

    refreshed_case = session.get(AlertCase, result.alert_case.id)
    assert refreshed_case is not None
    assert refreshed_case.queue_status is AlertQueueStatus.PENDING_REVIEW

    intervention_logs = list_intervention_logs(session, refreshed_case.id)
    assert len(intervention_logs) == 1
    assert intervention_logs[0].action_type is InterventionActionType.ADD_NOTE
    assert intervention_logs[0].action_note == "补充说明：已联系班主任核对近况。"

    audit_logs = list_audit_logs(session, refreshed_case.id)
    assert len(audit_logs) == 1
    assert audit_logs[0].action_code == "ADMIN_ADD_INTERVENTION_NOTE"

    session.close()


def test_close_case_rejects_pending_review_transition() -> None:
    """Pending cases should not skip directly to closed."""
    session, alert_case, admin = create_review_service_session()

    try:
        AlertReviewService(session).close_case(
            alert_case_id=alert_case.id,
            admin_user_id=admin.id,
            action_note="尝试直接结案。",
        )
    except InvalidAlertCaseTransitionError as exc:
        assert "cannot close alert case" in str(exc)
    else:
        raise AssertionError("expected InvalidAlertCaseTransitionError")

    refreshed_case = session.get(AlertCase, alert_case.id)
    assert refreshed_case is not None
    assert refreshed_case.queue_status is AlertQueueStatus.PENDING_REVIEW
    assert list_intervention_logs(session, alert_case.id) == []
    assert list_audit_logs(session, alert_case.id) == []

    session.close()
