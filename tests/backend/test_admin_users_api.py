"""Tests for administrator user-directory APIs."""

from __future__ import annotations

from datetime import datetime
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
from src.constants.treehole_enums import TreeholeAIStatus, TreeholePublishStatus
from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    AuditActorType,
    CaseSourceType,
    FocusListStatus,
    ReviewPriority,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import (
    AdminUser,
    AlertCase,
    AuditLog,
    Base,
    FocusListEntry,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)

PASSWORD_HASHER = PasswordHash.recommended()


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated admin-user API tests."""
    return Settings(
        APP_NAME="心语后台用户目录测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_admin_users_test_app(database_file: Path):
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


def seed_user_directory_data(app) -> dict[str, int]:
    """Insert students, submissions, posts, alerts, and focus entries."""
    with app.state.db_session_factory() as session:
        high_student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-user-1",
            display_nickname="Quiet Harbor",
            display_avatar_seed="seed-harbor",
            college_name="心理学院",
            class_name="2026级1班",
            consent_status=ConsentStatus.GRANTED,
            risk_status=StudentRiskStatus.HIGH,
            last_login_at=datetime(2026, 4, 28, 9, 0, 0),
        )
        watch_student = StudentUser(
            phone_e164="+8613812345688",
            wechat_openid="wx-user-2",
            display_nickname="Soft Cedar",
            display_avatar_seed="seed-cedar",
            college_name="计算机学院",
            class_name="2026级2班",
            consent_status=ConsentStatus.DECLINED,
            risk_status=StudentRiskStatus.WATCH,
            last_login_at=datetime(2026, 4, 27, 10, 0, 0),
        )
        normal_student = StudentUser(
            phone_e164="+8613812345698",
            wechat_openid="wx-user-3",
            display_nickname="Calm Moss",
            display_avatar_seed="seed-moss",
            college_name="外国语学院",
            class_name="2026级3班",
            consent_status=ConsentStatus.MISSING,
            risk_status=StudentRiskStatus.NORMAL,
            last_login_at=None,
        )
        session.add_all([high_student, watch_student, normal_student])
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
        sleep_template = QuestionnaireTemplate(
            code="SLEEP",
            name="睡眠问卷",
            category=QuestionnaireCategory.REQUIRED,
            question_count=15,
            scoring_mode=QuestionnaireScoringMode.SUM_0_3,
            unlock_required=True,
            is_active=True,
        )
        session.add_all([sds_template, sleep_template])
        session.flush()

        session.add_all(
            []
        )
        high_sds_submission = QuestionnaireSubmission(
            student_id=high_student.id,
            template_id=sds_template.id,
            started_at=datetime(2026, 4, 25, 8, 0, 0),
            submitted_at=datetime(2026, 4, 25, 8, 30, 0),
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=55,
            standardized_score=68,
            risk_level=QuestionnaireRiskLevel.HIGH,
            hard_trigger_hit=True,
            scoring_snapshot_json={"questionnaire_code": "SDS"},
        )
        high_sleep_submission = QuestionnaireSubmission(
            student_id=high_student.id,
            template_id=sleep_template.id,
            started_at=datetime(2026, 4, 24, 8, 0, 0),
            submitted_at=datetime(2026, 4, 24, 8, 20, 0),
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=16,
            standardized_score=None,
            risk_level=QuestionnaireRiskLevel.HIGH,
            hard_trigger_hit=False,
            scoring_snapshot_json={"questionnaire_code": "SLEEP"},
        )
        watch_sds_submission = QuestionnaireSubmission(
            student_id=watch_student.id,
            template_id=sds_template.id,
            started_at=datetime(2026, 4, 23, 8, 0, 0),
            submitted_at=datetime(2026, 4, 23, 8, 20, 0),
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=48,
            standardized_score=60,
            risk_level=QuestionnaireRiskLevel.WATCH,
            hard_trigger_hit=False,
            scoring_snapshot_json={"questionnaire_code": "SDS"},
        )
        session.add_all(
            [high_sds_submission, high_sleep_submission, watch_sds_submission]
        )

        high_treehole_post = TreeholePost(
            student_id=high_student.id,
            anonymous_name="匿名港湾",
            anonymous_avatar_key="harbor",
            content_raw="高风险树洞原文",
            content_masked=None,
            ai_status=TreeholeAIStatus.ANALYZED,
            publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
            risk_level=QuestionnaireRiskLevel.HIGH,
            allow_publication=False,
            hug_count=0,
            published_at=None,
        )
        watch_treehole_post = TreeholePost(
            student_id=watch_student.id,
            anonymous_name="匿名雪松",
            anonymous_avatar_key="cedar",
            content_raw="公开树洞原文",
            content_masked="公开树洞原文",
            ai_status=TreeholeAIStatus.MOCKED,
            publish_status=TreeholePublishStatus.PUBLISHED,
            risk_level=QuestionnaireRiskLevel.WATCH,
            allow_publication=True,
            hug_count=1,
            published_at=datetime(2026, 4, 26, 11, 0, 0),
        )
        session.add_all([high_treehole_post, watch_treehole_post])
        session.flush()

        session.add_all(
            [
                AlertCase(
                    student_id=high_student.id,
                    source_type=CaseSourceType.ASSESSMENT,
                    source_submission_id=high_sds_submission.id,
                    case_level=AlertCaseLevel.HIGH,
                    queue_status=AlertQueueStatus.PENDING_REVIEW,
                    review_priority=ReviewPriority.HIGHEST,
                    ai_reason_text="SDS 高风险。",
                ),
                AlertCase(
                    student_id=watch_student.id,
                    source_type=CaseSourceType.TREEHOLE,
                    source_post_id=watch_treehole_post.id,
                    case_level=AlertCaseLevel.HIGH,
                    queue_status=AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
                    review_priority=ReviewPriority.URGENT,
                    ai_reason_text="树洞需继续跟进。",
                ),
            ]
        )
        session.add_all(
            [
                FocusListEntry(
                    student_id=high_student.id,
                    source_type=CaseSourceType.ASSESSMENT,
                    source_id=high_sds_submission.id,
                    reason_code="SDS_POSITIVE",
                    reason_text="SDS 结果需关注",
                    status=FocusListStatus.ACTIVE,
                ),
                FocusListEntry(
                    student_id=watch_student.id,
                    source_type=CaseSourceType.TREEHOLE,
                    source_id=watch_treehole_post.id,
                    reason_code="TREEHOLE_AI_WATCH",
                    reason_text="树洞内容需关注",
                    status=FocusListStatus.ACTIVE,
                ),
            ]
        )
        session.commit()
        return {
            "high_student_id": high_student.id,
            "watch_student_id": watch_student.id,
            "normal_student_id": normal_student.id,
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


def test_list_users_filters_high_risk_and_returns_status_counts(tmp_path) -> None:
    """A06 list should filter by risk status while keeping global status counters."""
    app = create_admin_users_test_app(tmp_path / "admin-users-list.db")
    create_admin_user(app)
    identifiers = seed_user_directory_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        "/api/v1/admin/users",
        params={"risk_status": "high"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["applied_risk_status"] == "high"
    assert [item["student_id"] for item in payload["data"]["items"]] == [
        identifiers["high_student_id"]
    ]
    assert payload["data"]["items"][0]["student_label"].startswith("STU-")
    assert payload["data"]["items"][0]["masked_phone"].startswith("+8613")
    assert payload["data"]["status_counts"] == [
        {"risk_status": "high", "count": 1},
        {"risk_status": "watch", "count": 1},
        {"risk_status": "normal", "count": 1},
    ]


def test_user_detail_returns_masked_profile_and_writes_audit(tmp_path) -> None:
    """Opening A06 detail should keep the phone masked and append one audit event."""
    app = create_admin_users_test_app(tmp_path / "admin-users-detail.db")
    create_admin_user(app)
    identifiers = seed_user_directory_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        f"/api/v1/admin/users/{identifiers['high_student_id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    student = response.json()["data"]["student"]
    assert student["student_label"].startswith("STU-")
    assert student["masked_phone"].startswith("+8613")
    assert student["full_phone"] is None
    assert student["risk_status"] == "high"
    assert student["summary"]["active_focus_count"] == 1
    assert student["summary"]["open_alert_count"] == 1
    assert len(student["latest_questionnaires"]) >= 1
    assert len(student["latest_posts"]) >= 1

    with app.state.db_session_factory() as session:
        audit_logs = list_audit_logs(session)
        assert audit_logs[-1].actor_type is AuditActorType.ADMIN
        assert audit_logs[-1].action_code == "ADMIN_VIEW_USER_DETAIL"
        assert audit_logs[-1].target_type == "student_user"
        assert audit_logs[-1].target_id == identifiers["high_student_id"]


def test_reveal_user_phone_returns_full_number_and_writes_audit(tmp_path) -> None:
    """Explicit phone reveal should return the full phone and append one audit event."""
    app = create_admin_users_test_app(tmp_path / "admin-users-reveal.db")
    create_admin_user(app)
    identifiers = seed_user_directory_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.post(
        f"/api/v1/admin/users/{identifiers['watch_student_id']}/reveal-phone",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["student_id"] == identifiers["watch_student_id"]
    assert payload["full_phone"] == "+8613812345688"

    with app.state.db_session_factory() as session:
        audit_logs = list_audit_logs(session)
        assert audit_logs[-1].action_code == "ADMIN_REVEAL_STUDENT_PHONE"
        assert audit_logs[-1].target_type == "student_user"
        assert audit_logs[-1].target_id == identifiers["watch_student_id"]
