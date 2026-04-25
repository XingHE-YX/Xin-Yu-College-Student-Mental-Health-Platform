"""Tests for review workflow, intervention, focus-list, and audit ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from src.constants.account_enums import AdminRoleCode
from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionnaireSubmissionStatus,
)
from src.constants.treehole_enums import TreeholeAIStatus, TreeholePublishStatus
from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    AuditActorType,
    CaseSourceType,
    FocusListStatus,
    InterventionActionType,
    ReviewPriority,
)
from src.models import (
    AdminUser,
    AlertCase,
    AuditLog,
    Base,
    FocusListEntry,
    InterventionLog,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)


def test_review_workflow_tables_compile_to_mysql_contract() -> None:
    """The review workflow models should compile to the expected MySQL schema."""
    alert_sql = str(CreateTable(AlertCase.__table__).compile(dialect=mysql.dialect()))
    intervention_sql = str(
        CreateTable(InterventionLog.__table__).compile(dialect=mysql.dialect())
    )
    focus_sql = str(
        CreateTable(FocusListEntry.__table__).compile(dialect=mysql.dialect())
    )
    audit_sql = str(CreateTable(AuditLog.__table__).compile(dialect=mysql.dialect()))

    assert "ENUM('treehole','assessment','history')" in alert_sql
    assert (
        "ENUM('pending_review','confirmed_pending_intervention','dismissed_false_positive','closed')"
        in alert_sql
    )
    assert "ENUM('normal','urgent','highest')" in alert_sql
    assert "FOREIGN KEY(student_id) REFERENCES student_users (id)" in alert_sql
    assert "FOREIGN KEY(source_post_id) REFERENCES treehole_posts (id)" in alert_sql
    assert (
        "FOREIGN KEY(source_submission_id) REFERENCES questionnaire_submissions (id)"
        in alert_sql
    )
    assert "FOREIGN KEY(reviewed_by) REFERENCES admin_users (id)" in alert_sql
    assert (
        "ENUM('confirm_high_risk','dismiss_false_positive','simulate_contact','add_note','close_case')"
        in intervention_sql
    )
    assert "FOREIGN KEY(alert_case_id) REFERENCES alert_cases (id)" in intervention_sql
    assert "FOREIGN KEY(admin_user_id) REFERENCES admin_users (id)" in intervention_sql
    assert "ENUM('active','resolved')" in focus_sql
    assert "FOREIGN KEY(student_id) REFERENCES student_users (id)" in focus_sql
    assert "ENUM('student','admin','system')" in audit_sql
    assert "JSON" in audit_sql


def test_review_workflow_tables_persist_relationships_and_defaults() -> None:
    """Alert cases, intervention logs, focus entries, and audit logs should persist together."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            AdminUser.__table__,
            StudentUser.__table__,
            QuestionnaireTemplate.__table__,
            QuestionnaireSubmission.__table__,
            TreeholePost.__table__,
            AlertCase.__table__,
            InterventionLog.__table__,
            FocusListEntry.__table__,
            AuditLog.__table__,
        ],
    )
    inspector = inspect(engine)

    alert_foreign_keys = inspector.get_foreign_keys("alert_cases")
    intervention_foreign_keys = inspector.get_foreign_keys("intervention_logs")
    focus_foreign_keys = inspector.get_foreign_keys("focus_list_entries")
    audit_foreign_keys = inspector.get_foreign_keys("audit_logs")

    assert sorted(
        foreign_key["referred_table"] for foreign_key in alert_foreign_keys
    ) == [
        "admin_users",
        "questionnaire_submissions",
        "student_users",
        "treehole_posts",
    ]
    assert sorted(
        foreign_key["referred_table"] for foreign_key in intervention_foreign_keys
    ) == ["admin_users", "alert_cases"]
    assert focus_foreign_keys[0]["referred_table"] == "student_users"
    assert focus_foreign_keys[0]["constrained_columns"] == ["student_id"]
    assert audit_foreign_keys == []

    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-review-student",
            display_nickname="复核同学",
            display_avatar_seed="seed-review",
            college_name="心理学院",
            class_name="2026级1班",
        )
        admin = AdminUser(
            username="platform.admin",
            password_hash="argon2$review",
            role_code=AdminRoleCode.PLATFORM_ADMIN,
            display_name="平台管理员",
        )
        template = QuestionnaireTemplate(
            code="SDS",
            name="抑郁自评量表",
            category=QuestionnaireCategory.REQUIRED,
            question_count=20,
            scoring_mode=QuestionnaireScoringMode.ZUNG_STANDARD,
            unlock_required=True,
            is_active=True,
        )
        session.add_all([student, admin, template])
        session.flush()

        submission = QuestionnaireSubmission(
            student_id=student.id,
            template_id=template.id,
            started_at=now,
            submitted_at=now,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=56,
            standardized_score=70,
            risk_level=QuestionnaireRiskLevel.HIGH,
            hard_trigger_hit=True,
            scoring_snapshot_json={"raw_score": 56, "standardized_score": 70},
        )
        post = TreeholePost(
            student_id=student.id,
            anonymous_name="匿名树洞 03",
            anonymous_avatar_key="leaf-03",
            content_raw="最近反复觉得撑不住。",
            ai_status=TreeholeAIStatus.ANALYZED,
            publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
            risk_level=QuestionnaireRiskLevel.HIGH,
            allow_publication=False,
        )
        session.add_all([submission, post])
        session.flush()

        treehole_case = AlertCase(
            student_id=student.id,
            source_type=CaseSourceType.TREEHOLE,
            source_post_id=post.id,
            case_level=AlertCaseLevel.HIGH,
            queue_status=AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
            review_priority=ReviewPriority.HIGHEST,
            ai_reason_text="检测到明确高风险自伤暗示。",
            review_note="已确认高风险，准备模拟联系。",
            reviewed_by=admin.id,
            reviewed_at=now,
            simulated_notice_log="已模拟通知辅导员和值班老师。",
        )
        assessment_case = AlertCase(
            student_id=student.id,
            source_type=CaseSourceType.ASSESSMENT,
            source_submission_id=submission.id,
            case_level=AlertCaseLevel.HIGH,
        )
        focus_entry = FocusListEntry(
            student_id=student.id,
            source_type=CaseSourceType.TREEHOLE,
            source_id=post.id,
            reason_code="TREEHOLE_WATCH",
            reason_text="树洞文本呈现持续消极情绪，需要关注。",
        )
        audit_log = AuditLog(
            actor_type=AuditActorType.ADMIN,
            actor_id=admin.id,
            action_code="ADMIN_VIEW_SENSITIVE_ALERT_DETAIL",
            target_type="alert_case",
            target_id=1,
            metadata_json={"source": "A04", "confirmed": True},
            ip_address="127.0.0.1",
        )
        session.add_all([treehole_case, assessment_case, focus_entry, audit_log])
        session.flush()

        intervention_log = InterventionLog(
            alert_case_id=treehole_case.id,
            admin_user_id=admin.id,
            action_type=InterventionActionType.SIMULATE_CONTACT,
            action_note="已登记模拟通知动作。",
        )
        session.add(intervention_log)
        session.flush()
        session.refresh(student)
        session.refresh(admin)
        session.refresh(post)
        session.refresh(submission)

        assert assessment_case.queue_status is AlertQueueStatus.PENDING_REVIEW
        assert assessment_case.review_priority is ReviewPriority.NORMAL
        assert focus_entry.status is FocusListStatus.ACTIVE
        assert treehole_case.student.id == student.id
        assert treehole_case.source_post.id == post.id
        assert treehole_case.reviewer.id == admin.id
        assert assessment_case.source_submission.id == submission.id
        assert intervention_log.alert_case.id == treehole_case.id
        assert intervention_log.admin_user.id == admin.id
        assert len(treehole_case.intervention_logs) == 1
        assert student.alert_cases[0].id == treehole_case.id
        assert student.focus_list_entries[0].id == focus_entry.id
        assert admin.reviewed_alert_cases[0].id == treehole_case.id
        assert admin.intervention_logs[0].id == intervention_log.id
        assert audit_log.id is not None
        assert audit_log.metadata_json == {"source": "A04", "confirmed": True}

    engine.dispose()
