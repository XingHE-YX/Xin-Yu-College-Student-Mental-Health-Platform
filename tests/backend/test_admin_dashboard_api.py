"""Tests for the administrator dashboard summary API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from src.constants.account_enums import AdminRoleCode, StudentRiskStatus
from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionnaireSubmissionStatus,
)
from src.constants.treehole_enums import TreeholePublishStatus
from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    CaseSourceType,
    FocusListStatus,
    ReviewPriority,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import (
    AdminUser,
    AlertCase,
    Base,
    FocusListEntry,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)
from src.models.base import utc_now

PASSWORD_HASHER = PasswordHash.recommended()


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated admin-dashboard API tests."""
    return Settings(
        APP_NAME="心语后台总览测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_dashboard_test_app(database_file: Path):
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


def seed_dashboard_data(app) -> None:
    """Insert alert, focus, student, post, and questionnaire summary fixtures."""
    now = utc_now()
    with app.state.db_session_factory() as session:
        students = [
            StudentUser(
                phone_e164="+8613900000001",
                wechat_openid="openid-1",
                display_nickname="Quiet Ginkgo",
                display_avatar_seed="avatar-1",
                college_name="心理学院",
                class_name="2026-1",
                risk_status=StudentRiskStatus.HIGH,
            ),
            StudentUser(
                phone_e164="+8613900000002",
                wechat_openid="openid-2",
                display_nickname="Calm Cedar",
                display_avatar_seed="avatar-2",
                college_name="心理学院",
                class_name="2026-2",
                risk_status=StudentRiskStatus.NORMAL,
            ),
            StudentUser(
                phone_e164="+8613900000003",
                wechat_openid="openid-3",
                display_nickname="Gentle Harbor",
                display_avatar_seed="avatar-3",
                college_name="心理学院",
                class_name="2026-3",
                risk_status=StudentRiskStatus.HIGH,
            ),
        ]
        session.add_all(students)
        session.flush()

        template = QuestionnaireTemplate(
            code="SCREEN",
            name="快速筛查",
            category=QuestionnaireCategory.REQUIRED,
            question_count=15,
            scoring_mode=QuestionnaireScoringMode.SUM_1_5,
            unlock_required=True,
            is_active=True,
        )
        session.add(template)
        session.flush()

        submissions = [
            QuestionnaireSubmission(
                student_id=students[0].id,
                template_id=template.id,
                started_at=now,
                submitted_at=now,
                status=QuestionnaireSubmissionStatus.SUBMITTED,
                raw_score=52,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.WATCH,
                hard_trigger_hit=False,
                scoring_snapshot_json={"raw_score": 52},
            ),
            QuestionnaireSubmission(
                student_id=students[1].id,
                template_id=template.id,
                started_at=now,
                submitted_at=now,
                status=QuestionnaireSubmissionStatus.SUBMITTED,
                raw_score=66,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.HIGH,
                hard_trigger_hit=True,
                scoring_snapshot_json={"raw_score": 66},
            ),
            QuestionnaireSubmission(
                student_id=students[2].id,
                template_id=template.id,
                started_at=now,
                submitted_at=now,
                status=QuestionnaireSubmissionStatus.SUBMITTED,
                raw_score=40,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.LOW,
                hard_trigger_hit=False,
                scoring_snapshot_json={"raw_score": 40},
            ),
        ]
        session.add_all(submissions)
        session.flush()

        alert_cases = [
            AlertCase(
                student_id=students[0].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[0].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.PENDING_REVIEW,
                review_priority=ReviewPriority.HIGHEST,
                ai_reason_text="高风险筛查信号",
            ),
            AlertCase(
                student_id=students[1].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[1].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.PENDING_REVIEW,
                review_priority=ReviewPriority.NORMAL,
                ai_reason_text="需要人工复核",
            ),
            AlertCase(
                student_id=students[2].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[2].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
                review_priority=ReviewPriority.URGENT,
                ai_reason_text="已确认高风险",
            ),
            AlertCase(
                student_id=students[2].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[2].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.CLOSED,
                review_priority=ReviewPriority.NORMAL,
                ai_reason_text="已结案",
            ),
            AlertCase(
                student_id=students[1].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[1].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
                review_priority=ReviewPriority.NORMAL,
                ai_reason_text="误报",
            ),
        ]
        session.add_all(alert_cases)

        focus_entries = [
            FocusListEntry(
                student_id=students[0].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_id=submissions[0].id,
                reason_code="SDS_WATCH",
                reason_text="SDS 结果需关注",
                status=FocusListStatus.ACTIVE,
            ),
            FocusListEntry(
                student_id=students[1].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_id=submissions[1].id,
                reason_code="SAS_WATCH",
                reason_text="SAS 结果需关注",
                status=FocusListStatus.ACTIVE,
            ),
            FocusListEntry(
                student_id=students[1].id,
                source_type=CaseSourceType.HISTORY,
                source_id=9001,
                reason_code="HISTORY_HIGH_REVIEW",
                reason_text="历史高风险复查",
                status=FocusListStatus.ACTIVE,
            ),
            FocusListEntry(
                student_id=students[2].id,
                source_type=CaseSourceType.TREEHOLE,
                source_id=8001,
                reason_code="TREEHOLE_REVIEWED",
                reason_text="树洞需关注记录已归档",
                status=FocusListStatus.RESOLVED,
            ),
        ]
        session.add_all(focus_entries)

        posts = [
            TreeholePost(
                student_id=students[0].id,
                anonymous_name="匿名银杏",
                anonymous_avatar_key="ginkgo",
                content_raw="今天情绪平稳。",
                content_masked="今天情绪平稳。",
                risk_level=QuestionnaireRiskLevel.LOW,
                publish_status=TreeholePublishStatus.PUBLISHED,
                allow_publication=True,
                published_at=now,
            ),
            TreeholePost(
                student_id=students[1].id,
                anonymous_name="匿名雪松",
                anonymous_avatar_key="cedar",
                content_raw="想找个人聊聊。",
                content_masked="想找个人聊聊。",
                risk_level=QuestionnaireRiskLevel.WATCH,
                publish_status=TreeholePublishStatus.PUBLISHED,
                allow_publication=True,
                published_at=now,
            ),
            TreeholePost(
                student_id=students[2].id,
                anonymous_name="匿名港湾",
                anonymous_avatar_key="harbor",
                content_raw="我现在很危险。",
                content_masked=None,
                risk_level=QuestionnaireRiskLevel.HIGH,
                publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
                allow_publication=False,
            ),
            TreeholePost(
                student_id=students[2].id,
                anonymous_name="匿名山岚",
                anonymous_avatar_key="dawn",
                content_raw="这条内容已被删除。",
                content_masked="这条内容已被删除。",
                risk_level=QuestionnaireRiskLevel.LOW,
                publish_status=TreeholePublishStatus.DELETED_BY_USER,
                allow_publication=False,
            ),
        ]
        session.add_all(posts)
        session.commit()


def login_admin(client: TestClient) -> str:
    """Authenticate the fixture admin user and return the bearer token."""
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "platform.admin", "password": "Admin#2026"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_admin_dashboard_summary_returns_live_counts(tmp_path) -> None:
    """The dashboard summary endpoint should aggregate the A02 KPI metrics."""
    app = create_dashboard_test_app(tmp_path / "admin-dashboard-summary.db")
    create_admin_user(app)
    seed_dashboard_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        "/api/v1/admin/dashboard/summary",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    summary = payload["data"]["summary"]
    assert summary["generated_at"] is not None

    assert summary["kpis"] == {
        "pending_review_count": 2,
        "open_high_risk_case_count": 3,
        "confirmed_high_risk_count": 1,
        "focus_student_count": 2,
        "published_post_count": 2,
    }
    assert summary["stats"] == {
        "highest_priority_pending_count": 1,
        "blocked_post_count": 1,
        "high_risk_student_count": 2,
        "questionnaire_submission_count": 3,
    }


def test_admin_dashboard_summary_requires_bearer_token(tmp_path) -> None:
    """Unauthenticated dashboard summary requests should be rejected."""
    app = create_dashboard_test_app(tmp_path / "admin-dashboard-auth.db")
    client = TestClient(app)

    response = client.get("/api/v1/admin/dashboard/summary")

    assert response.status_code == 401
    assert response.json()["detail"] == "admin access token is required"
