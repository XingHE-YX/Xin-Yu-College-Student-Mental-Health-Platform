"""Tests for administrator alert queue and detail APIs."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import select

from src.constants.account_enums import AdminRoleCode, ConsentStatus, StudentRiskStatus
from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionnaireSubmissionStatus,
)
from src.constants.treehole_enums import (
    AIAnalysisProvider,
    AIAnalysisTargetType,
    AIRecommendedAction,
    TreeholePublishStatus,
)
from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    AuditActorType,
    CaseSourceType,
    InterventionActionType,
    ReviewPriority,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import (
    AIAnalysisRecord,
    AdminUser,
    AlertCase,
    AuditLog,
    Base,
    InterventionLog,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)
from src.models.base import utc_now

PASSWORD_HASHER = PasswordHash.recommended()


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated admin-alert API tests."""
    return Settings(
        APP_NAME="心语后台预警队列测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_admin_alerts_test_app(database_file: Path):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(build_settings(database_file))
    Base.metadata.create_all(app.state.db_engine)
    return app


def create_admin_user(app) -> AdminUser:
    """Insert one active administrator row with a valid Argon2 password hash."""
    with app.state.db_session_factory() as session:
        admin = AdminUser(
            username="platform.admin",
            password_hash=PASSWORD_HASHER.hash("Admin#2026"),
            role_code=AdminRoleCode.PLATFORM_ADMIN,
            display_name="平台管理员",
            is_active=True,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        return admin


def seed_alert_workflow_data(app) -> dict[str, int]:
    """Insert students, alert sources, queue rows, and timeline fixtures."""
    now = utc_now()
    with app.state.db_session_factory() as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-alert-student",
            display_nickname="Quiet Harbor",
            display_avatar_seed="seed-harbor",
            college_name="心理学院",
            class_name="2026级1班",
            consent_status=ConsentStatus.GRANTED,
            risk_status=StudentRiskStatus.HIGH,
        )
        other_student = StudentUser(
            phone_e164="+8613812345688",
            wechat_openid="wx-alert-student-2",
            display_nickname="Soft Cedar",
            display_avatar_seed="seed-cedar",
            college_name="计算机学院",
            class_name="2026级2班",
            consent_status=ConsentStatus.GRANTED,
            risk_status=StudentRiskStatus.WATCH,
        )
        session.add_all([student, other_student])
        session.flush()

        sds_template = QuestionnaireTemplate(
            code="SDS",
            name="抑郁自评量表",
            category=QuestionnaireCategory.REQUIRED,
            question_count=20,
            scoring_mode=QuestionnaireScoringMode.ZUNG_STANDARD,
            unlock_required=True,
            is_active=True,
        )
        sas_template = QuestionnaireTemplate(
            code="SAS",
            name="焦虑自评量表",
            category=QuestionnaireCategory.REQUIRED,
            question_count=20,
            scoring_mode=QuestionnaireScoringMode.ZUNG_STANDARD,
            unlock_required=True,
            is_active=True,
        )
        session.add_all([sds_template, sas_template])
        session.flush()

        current_sds_submission = QuestionnaireSubmission(
            student_id=student.id,
            template_id=sds_template.id,
            started_at=now,
            submitted_at=now,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=54,
            standardized_score=68,
            risk_level=QuestionnaireRiskLevel.HIGH,
            hard_trigger_hit=True,
            scoring_snapshot_json={
                "questionnaire_code": "SDS",
                "hard_trigger_hit": True,
                "hard_trigger_matches": [
                    {
                        "question_code": "SDS_15",
                        "reason_code": "HT-02",
                        "matched_value": 4,
                    }
                ],
            },
        )
        prior_sas_submission = QuestionnaireSubmission(
            student_id=student.id,
            template_id=sas_template.id,
            started_at=now,
            submitted_at=now,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=50,
            standardized_score=63,
            risk_level=QuestionnaireRiskLevel.HIGH,
            hard_trigger_hit=False,
            scoring_snapshot_json={
                "questionnaire_code": "SAS",
                "hard_trigger_hit": False,
                "hard_trigger_matches": [],
            },
        )
        other_student_submission = QuestionnaireSubmission(
            student_id=other_student.id,
            template_id=sds_template.id,
            started_at=now,
            submitted_at=now,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=48,
            standardized_score=60,
            risk_level=QuestionnaireRiskLevel.WATCH,
            hard_trigger_hit=False,
            scoring_snapshot_json={"questionnaire_code": "SDS"},
        )
        session.add_all(
            [current_sds_submission, prior_sas_submission, other_student_submission]
        )
        session.flush()

        current_treehole_post = TreeholePost(
            student_id=student.id,
            anonymous_name="匿名港湾",
            anonymous_avatar_key="harbor",
            content_raw="我现在真的很危险，已经不想继续撑下去了。",
            content_masked="我现在真的很危险，已经不想继续撑下去了。",
            risk_level=QuestionnaireRiskLevel.HIGH,
            publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
            allow_publication=False,
        )
        previous_treehole_post = TreeholePost(
            student_id=student.id,
            anonymous_name="匿名雪松",
            anonymous_avatar_key="cedar",
            content_raw="上周也有过类似念头。",
            content_masked="上周也有过类似念头。",
            risk_level=QuestionnaireRiskLevel.HIGH,
            publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
            allow_publication=False,
        )
        other_student_treehole_post = TreeholePost(
            student_id=other_student.id,
            anonymous_name="匿名苔藓",
            anonymous_avatar_key="moss",
            content_raw="今天想找人聊聊。",
            content_masked="今天想找人聊聊。",
            risk_level=QuestionnaireRiskLevel.WATCH,
            publish_status=TreeholePublishStatus.PUBLISHED,
            allow_publication=True,
        )
        session.add_all(
            [current_treehole_post, previous_treehole_post, other_student_treehole_post]
        )
        session.flush()

        ai_analysis = AIAnalysisRecord(
            target_type=AIAnalysisTargetType.TREEHOLE_POST,
            target_id=current_treehole_post.id,
            provider=AIAnalysisProvider.DEEPSEEK,
            model_name="deepseek-v4-flash",
            request_payload_json={"content": current_treehole_post.content_raw},
            response_raw_json={"risk_level": "high"},
            parsed_risk_level=QuestionnaireRiskLevel.HIGH,
            parsed_risk_score=Decimal("0.9621"),
            emotion_tags_json=["绝望", "孤立"],
            trigger_phrases_json=["不想继续撑下去了"],
            reason_text="文本出现了持续性绝望和自伤风险信号。",
            recommended_action=AIRecommendedAction.MANUAL_REVIEW_HIGH,
            fallback_used=False,
        )
        session.add(ai_analysis)
        session.flush()

        pending_treehole_alert = AlertCase(
            student_id=student.id,
            source_type=CaseSourceType.TREEHOLE,
            source_post_id=current_treehole_post.id,
            case_level=AlertCaseLevel.HIGH,
            queue_status=AlertQueueStatus.PENDING_REVIEW,
            review_priority=ReviewPriority.HIGHEST,
            ai_reason_text="树洞内容出现强烈危险信号。",
        )
        pending_assessment_alert = AlertCase(
            student_id=student.id,
            source_type=CaseSourceType.ASSESSMENT,
            source_submission_id=current_sds_submission.id,
            case_level=AlertCaseLevel.HIGH,
            queue_status=AlertQueueStatus.PENDING_REVIEW,
            review_priority=ReviewPriority.HIGHEST,
            ai_reason_text="SDS 高风险且命中硬触发。",
        )
        confirmed_alert = AlertCase(
            student_id=other_student.id,
            source_type=CaseSourceType.ASSESSMENT,
            source_submission_id=other_student_submission.id,
            case_level=AlertCaseLevel.HIGH,
            queue_status=AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
            review_priority=ReviewPriority.URGENT,
            ai_reason_text="已确认，需要跟进。",
            review_note="已确认高风险。",
            simulated_notice_log="[SIMULATED] Notification recorded for counselor follow-up.",
        )
        dismissed_alert = AlertCase(
            student_id=other_student.id,
            source_type=CaseSourceType.TREEHOLE,
            source_post_id=other_student_treehole_post.id,
            case_level=AlertCaseLevel.HIGH,
            queue_status=AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
            review_priority=ReviewPriority.NORMAL,
            ai_reason_text="上下文不足。",
            review_note="误报。",
        )
        closed_alert = AlertCase(
            student_id=other_student.id,
            source_type=CaseSourceType.ASSESSMENT,
            source_submission_id=other_student_submission.id,
            case_level=AlertCaseLevel.HIGH,
            queue_status=AlertQueueStatus.CLOSED,
            review_priority=ReviewPriority.NORMAL,
            ai_reason_text="已结案。",
            review_note="已完成跟进。",
        )
        session.add_all(
            [
                pending_treehole_alert,
                pending_assessment_alert,
                confirmed_alert,
                dismissed_alert,
                closed_alert,
            ]
        )
        session.flush()

        session.add(
            InterventionLog(
                alert_case_id=confirmed_alert.id,
                admin_user_id=1,
                action_type=InterventionActionType.SIMULATE_CONTACT,
                action_note="已写入模拟联系记录。",
            )
        )
        session.commit()
        return {
            "pending_treehole_alert_id": pending_treehole_alert.id,
            "pending_assessment_alert_id": pending_assessment_alert.id,
            "confirmed_alert_id": confirmed_alert.id,
        }


def login_admin(client: TestClient) -> str:
    """Authenticate the seeded administrator and return the bearer token."""
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "platform.admin", "password": "Admin#2026"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def list_audit_logs(session) -> list[AuditLog]:
    """Return all audit logs in insertion order."""
    return list(session.scalars(select(AuditLog).order_by(AuditLog.id.asc())).all())


def test_list_alerts_filters_pending_and_returns_status_counts(tmp_path) -> None:
    """The A03 list route should filter by status and keep global status counts."""
    app = create_admin_alerts_test_app(tmp_path / "admin-alerts-list.db")
    create_admin_user(app)
    identifiers = seed_alert_workflow_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        "/api/v1/admin/alerts",
        params={"queue_status": "pending_review"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["applied_queue_status"] == "pending_review"
    assert [item["alert_id"] for item in payload["data"]["items"]] == [
        identifiers["pending_assessment_alert_id"],
        identifiers["pending_treehole_alert_id"],
    ]
    assert payload["data"]["items"][0]["review_priority"] == "highest"
    assert payload["data"]["items"][0]["source_type"] == "assessment"
    assert payload["data"]["items"][1]["source_type"] == "treehole"
    assert payload["data"]["status_counts"] == [
        {"queue_status": "pending_review", "count": 2},
        {"queue_status": "confirmed_pending_intervention", "count": 1},
        {"queue_status": "dismissed_false_positive", "count": 1},
        {"queue_status": "closed", "count": 1},
    ]


def test_alert_detail_returns_masked_treehole_context_and_writes_audit(tmp_path) -> None:
    """Opening A04 detail should return masked context and persist a view audit log."""
    app = create_admin_alerts_test_app(tmp_path / "admin-alerts-detail-treehole.db")
    create_admin_user(app)
    identifiers = seed_alert_workflow_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        f"/api/v1/admin/alerts/{identifiers['pending_treehole_alert_id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    alert_detail = response.json()["data"]["alert"]
    assert alert_detail["queue_status"] == "pending_review"
    assert alert_detail["student"]["student_label"].startswith("STU-")
    assert alert_detail["student"]["masked_phone"].startswith("+8613")
    assert alert_detail["source"]["kind"] == "treehole"
    assert alert_detail["source"]["full_content"] is None
    assert alert_detail["source"]["full_content_available"] is True
    assert alert_detail["source"]["ai_analysis"]["parsed_risk_level"] == "high"
    assert "不想继续撑下去了" in alert_detail["source"]["ai_analysis"]["trigger_phrases"]
    assert alert_detail["history"]["has_history_high_risk"] is True
    assert len(alert_detail["history"]["latest_questionnaires"]) >= 2
    assert alert_detail["action_permissions"] == {
        "can_confirm": True,
        "can_dismiss": True,
        "can_close": False,
        "can_add_note": True,
    }

    with app.state.db_session_factory() as session:
        audit_logs = list_audit_logs(session)
        assert audit_logs[-1].actor_type is AuditActorType.ADMIN
        assert audit_logs[-1].action_code == "ADMIN_VIEW_ALERT_CASE_DETAIL"
        assert audit_logs[-1].target_type == "alert_case"
        assert audit_logs[-1].target_id == identifiers["pending_treehole_alert_id"]


def test_reveal_alert_content_returns_raw_text_and_writes_audit(tmp_path) -> None:
    """Explicit raw-content reveal should return `content_raw` and append an audit event."""
    app = create_admin_alerts_test_app(tmp_path / "admin-alerts-reveal.db")
    create_admin_user(app)
    identifiers = seed_alert_workflow_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.post(
        f"/api/v1/admin/alerts/{identifiers['pending_treehole_alert_id']}/reveal-content",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["alert_id"] == identifiers["pending_treehole_alert_id"]
    assert payload["source_type"] == "treehole"
    assert "不想继续撑下去了" in payload["full_content"]

    with app.state.db_session_factory() as session:
        audit_logs = list_audit_logs(session)
        assert audit_logs[-1].action_code == "ADMIN_REVEAL_ALERT_SOURCE_CONTENT"
        assert audit_logs[-1].target_type == "treehole_post"


def test_assessment_alert_detail_includes_scoring_snapshot_and_history(tmp_path) -> None:
    """Assessment-source alerts should expose questionnaire details and hard-trigger metadata."""
    app = create_admin_alerts_test_app(tmp_path / "admin-alerts-detail-assessment.db")
    create_admin_user(app)
    identifiers = seed_alert_workflow_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        f"/api/v1/admin/alerts/{identifiers['pending_assessment_alert_id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    source = response.json()["data"]["alert"]["source"]
    assert source["kind"] == "assessment"
    assert source["questionnaire_code"] == "SDS"
    assert source["questionnaire_name"] == "抑郁自评量表"
    assert source["hard_trigger_hit"] is True
    assert source["hard_trigger_matches"][0]["reason_code"] == "HT-02"
    assert source["result_summary"] == "原始分 54，标准分 68"


def test_confirm_note_and_close_routes_complete_review_flow(tmp_path) -> None:
    """One alert should support confirm, add-note, and close actions end-to-end."""
    app = create_admin_alerts_test_app(tmp_path / "admin-alerts-actions.db")
    create_admin_user(app)
    identifiers = seed_alert_workflow_data(app)
    client = TestClient(app)
    access_token = login_admin(client)
    alert_id = identifiers["pending_treehole_alert_id"]

    confirm_response = client.post(
        f"/api/v1/admin/alerts/{alert_id}/confirm",
        json={
            "review_note": "人工复核确认存在持续性危险表达。",
            "intervention_note": "已记录给辅导员的模拟联系说明。",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert confirm_response.status_code == 200
    confirm_payload = confirm_response.json()["data"]
    assert confirm_payload["queue_status"] == "confirmed_pending_intervention"
    assert "[SIMULATED]" in confirm_payload["simulated_notice_log"]

    note_response = client.post(
        f"/api/v1/admin/alerts/{alert_id}/notes",
        json={"action_note": "已安排次日继续跟进。"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert note_response.status_code == 200
    assert note_response.json()["data"]["queue_status"] == "confirmed_pending_intervention"

    close_response = client.post(
        f"/api/v1/admin/alerts/{alert_id}/close",
        json={"action_note": "案例已完成本轮跟进，转入结案。"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert close_response.status_code == 200
    assert close_response.json()["data"]["queue_status"] == "closed"

    with app.state.db_session_factory() as session:
        refreshed_case = session.get(AlertCase, alert_id)
        assert refreshed_case is not None
        assert refreshed_case.queue_status is AlertQueueStatus.CLOSED
        intervention_logs = list(
            session.scalars(
                select(InterventionLog)
                .where(InterventionLog.alert_case_id == alert_id)
                .order_by(InterventionLog.id.asc())
            ).all()
        )
        assert [log.action_type for log in intervention_logs] == [
            InterventionActionType.CONFIRM_HIGH_RISK,
            InterventionActionType.SIMULATE_CONTACT,
            InterventionActionType.ADD_NOTE,
            InterventionActionType.CLOSE_CASE,
        ]


def test_dismiss_rejects_already_confirmed_case(tmp_path) -> None:
    """Dismiss actions should return 409 once the case has already been confirmed."""
    app = create_admin_alerts_test_app(tmp_path / "admin-alerts-conflict.db")
    create_admin_user(app)
    identifiers = seed_alert_workflow_data(app)
    client = TestClient(app)
    access_token = login_admin(client)
    alert_id = identifiers["pending_treehole_alert_id"]

    confirm_response = client.post(
        f"/api/v1/admin/alerts/{alert_id}/confirm",
        json={
            "review_note": "人工复核确认存在持续性危险表达。",
            "intervention_note": "已记录给辅导员的模拟联系说明。",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert confirm_response.status_code == 200

    dismiss_response = client.post(
        f"/api/v1/admin/alerts/{alert_id}/dismiss",
        json={"review_note": "尝试改为误报。"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert dismiss_response.status_code == 409
    payload = dismiss_response.json()
    assert payload["code"] == "ALERT_CASE_TRANSITION_CONFLICT"
