"""Tests for the administrator analytics API."""

from __future__ import annotations

from datetime import datetime, timedelta
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
    ReviewPriority,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import (
    AdminUser,
    AlertCase,
    Base,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)

PASSWORD_HASHER = PasswordHash.recommended()


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated admin-analytics API tests."""
    return Settings(
        APP_NAME="心语后台统计测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_analytics_test_app(database_file: Path):
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


def seed_analytics_data(app, *, now: datetime) -> None:
    """Insert deterministic students, posts, submissions, and alert fixtures."""

    def at(days_ago: int, *, hour: int) -> datetime:
        return now.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(
            days=days_ago
        )

    with app.state.db_session_factory() as session:
        students = [
            StudentUser(
                phone_e164="+8613900000101",
                wechat_openid="analytics-openid-1",
                display_nickname="Quiet Ginkgo",
                display_avatar_seed="avatar-1",
                college_name="心理学院",
                class_name="2026-1",
                risk_status=StudentRiskStatus.NORMAL,
            ),
            StudentUser(
                phone_e164="+8613900000102",
                wechat_openid="analytics-openid-2",
                display_nickname="Calm Cedar",
                display_avatar_seed="avatar-2",
                college_name="心理学院",
                class_name="2026-2",
                risk_status=StudentRiskStatus.WATCH,
            ),
            StudentUser(
                phone_e164="+8613900000103",
                wechat_openid="analytics-openid-3",
                display_nickname="Gentle Harbor",
                display_avatar_seed="avatar-3",
                college_name="心理学院",
                class_name="2026-3",
                risk_status=StudentRiskStatus.HIGH,
            ),
            StudentUser(
                phone_e164="+8613900000104",
                wechat_openid="analytics-openid-4",
                display_nickname="Still Dawn",
                display_avatar_seed="avatar-4",
                college_name="心理学院",
                class_name="2026-4",
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
                started_at=at(0, hour=8),
                submitted_at=at(0, hour=9),
                status=QuestionnaireSubmissionStatus.SUBMITTED,
                raw_score=42,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.LOW,
                hard_trigger_hit=False,
                scoring_snapshot_json={"raw_score": 42},
            ),
            QuestionnaireSubmission(
                student_id=students[1].id,
                template_id=template.id,
                started_at=at(2, hour=10),
                submitted_at=at(2, hour=11),
                status=QuestionnaireSubmissionStatus.SUBMITTED,
                raw_score=55,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.WATCH,
                hard_trigger_hit=False,
                scoring_snapshot_json={"raw_score": 55},
            ),
            QuestionnaireSubmission(
                student_id=students[2].id,
                template_id=template.id,
                started_at=at(6, hour=13),
                submitted_at=at(6, hour=14),
                status=QuestionnaireSubmissionStatus.SUBMITTED,
                raw_score=68,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.HIGH,
                hard_trigger_hit=True,
                scoring_snapshot_json={"raw_score": 68},
            ),
            QuestionnaireSubmission(
                student_id=students[3].id,
                template_id=template.id,
                started_at=at(8, hour=9),
                submitted_at=at(8, hour=10),
                status=QuestionnaireSubmissionStatus.SUBMITTED,
                raw_score=40,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.LOW,
                hard_trigger_hit=False,
                scoring_snapshot_json={"raw_score": 40},
            ),
        ]
        session.add_all(submissions)

        posts = [
            TreeholePost(
                student_id=students[0].id,
                anonymous_name="匿名银杏",
                anonymous_avatar_key="ginkgo",
                content_raw="今天状态还可以。",
                content_masked="今天状态还可以。",
                risk_level=QuestionnaireRiskLevel.LOW,
                publish_status=TreeholePublishStatus.PUBLISHED,
                allow_publication=True,
                published_at=at(0, hour=15),
                created_at=at(0, hour=15),
                updated_at=at(0, hour=15),
            ),
            TreeholePost(
                student_id=students[1].id,
                anonymous_name="匿名雪松",
                anonymous_avatar_key="cedar",
                content_raw="这两天有点累。",
                content_masked="这两天有点累。",
                risk_level=QuestionnaireRiskLevel.WATCH,
                publish_status=TreeholePublishStatus.PUBLISHED,
                allow_publication=True,
                published_at=at(1, hour=16),
                created_at=at(1, hour=16),
                updated_at=at(1, hour=16),
            ),
            TreeholePost(
                student_id=students[2].id,
                anonymous_name="匿名港湾",
                anonymous_avatar_key="harbor",
                content_raw="需要帮助。",
                content_masked=None,
                risk_level=QuestionnaireRiskLevel.HIGH,
                publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
                allow_publication=False,
                created_at=at(6, hour=17),
                updated_at=at(6, hour=17),
            ),
            TreeholePost(
                student_id=students[3].id,
                anonymous_name="匿名山岚",
                anonymous_avatar_key="dawn",
                content_raw="这条内容不在统计窗口内。",
                content_masked="这条内容不在统计窗口内。",
                risk_level=QuestionnaireRiskLevel.LOW,
                publish_status=TreeholePublishStatus.DELETED_BY_USER,
                allow_publication=False,
                deleted_at=at(10, hour=18),
                created_at=at(10, hour=18),
                updated_at=at(10, hour=18),
            ),
        ]
        session.add_all(posts)
        session.flush()

        alert_cases = [
            AlertCase(
                student_id=students[0].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[0].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.PENDING_REVIEW,
                review_priority=ReviewPriority.HIGHEST,
                ai_reason_text="今日进入待复核",
                created_at=at(0, hour=18),
                updated_at=at(0, hour=18),
            ),
            AlertCase(
                student_id=students[1].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[1].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
                review_priority=ReviewPriority.URGENT,
                ai_reason_text="已确认待干预",
                created_at=at(1, hour=18),
                updated_at=at(1, hour=18),
            ),
            AlertCase(
                student_id=students[2].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[2].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
                review_priority=ReviewPriority.NORMAL,
                ai_reason_text="已判定误报",
                created_at=at(3, hour=18),
                updated_at=at(3, hour=18),
            ),
            AlertCase(
                student_id=students[3].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[3].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.CLOSED,
                review_priority=ReviewPriority.NORMAL,
                ai_reason_text="已结案归档",
                created_at=at(6, hour=19),
                updated_at=at(6, hour=19),
            ),
            AlertCase(
                student_id=students[3].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions[3].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.PENDING_REVIEW,
                review_priority=ReviewPriority.NORMAL,
                ai_reason_text="窗口外待复核案例",
                created_at=at(12, hour=20),
                updated_at=at(12, hour=20),
            ),
        ]
        session.add_all(alert_cases)
        session.commit()


def login_admin(client: TestClient) -> str:
    """Authenticate the fixture admin user and return the bearer token."""
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "platform.admin", "password": "Admin#2026"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_admin_analytics_trends_returns_chart_ready_aggregates(
    tmp_path,
    monkeypatch,
) -> None:
    """The analytics endpoint should expose real risk, trend, and alert metrics."""
    fixed_now = datetime(2026, 4, 29, 10, 30, 0)
    monkeypatch.setattr(
        "src.services.admin_analytics_service.utc_now",
        lambda: fixed_now,
    )

    app = create_analytics_test_app(tmp_path / "admin-analytics.db")
    create_admin_user(app)
    seed_analytics_data(app, now=fixed_now)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        "/api/v1/admin/analytics/trends",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"

    analytics = payload["data"]["analytics"]
    assert analytics["generated_at"] == "2026-04-29T10:30:00"
    assert analytics["risk_distribution"] == {
        "total_students": 4,
        "items": [
            {"risk_status": "normal", "student_count": 1},
            {"risk_status": "watch", "student_count": 1},
            {"risk_status": "high", "student_count": 2},
        ],
    }
    assert analytics["alert_processing"] == {
        "total_alert_case_count": 5,
        "items": [
            {"queue_status": "pending_review", "case_count": 2},
            {
                "queue_status": "confirmed_pending_intervention",
                "case_count": 1,
            },
            {"queue_status": "dismissed_false_positive", "case_count": 1},
            {"queue_status": "closed", "case_count": 1},
        ],
    }

    daily_trends = analytics["daily_trends"]
    assert daily_trends["window_days"] == 7
    assert daily_trends["start_date"] == "2026-04-23"
    assert daily_trends["end_date"] == "2026-04-29"
    assert len(daily_trends["items"]) == 7

    trend_items = {item["date"]: item for item in daily_trends["items"]}
    assert trend_items["2026-04-23"] == {
        "date": "2026-04-23",
        "questionnaire_submission_count": 1,
        "treehole_post_count": 1,
        "alert_case_count": 1,
    }
    assert trend_items["2026-04-24"] == {
        "date": "2026-04-24",
        "questionnaire_submission_count": 0,
        "treehole_post_count": 0,
        "alert_case_count": 0,
    }
    assert trend_items["2026-04-25"] == {
        "date": "2026-04-25",
        "questionnaire_submission_count": 0,
        "treehole_post_count": 0,
        "alert_case_count": 0,
    }
    assert trend_items["2026-04-26"] == {
        "date": "2026-04-26",
        "questionnaire_submission_count": 0,
        "treehole_post_count": 0,
        "alert_case_count": 1,
    }
    assert trend_items["2026-04-27"] == {
        "date": "2026-04-27",
        "questionnaire_submission_count": 1,
        "treehole_post_count": 0,
        "alert_case_count": 0,
    }
    assert trend_items["2026-04-28"] == {
        "date": "2026-04-28",
        "questionnaire_submission_count": 0,
        "treehole_post_count": 1,
        "alert_case_count": 1,
    }
    assert trend_items["2026-04-29"] == {
        "date": "2026-04-29",
        "questionnaire_submission_count": 1,
        "treehole_post_count": 1,
        "alert_case_count": 1,
    }


def test_admin_analytics_trends_requires_bearer_token(tmp_path) -> None:
    """Unauthenticated analytics requests should be rejected."""
    app = create_analytics_test_app(tmp_path / "admin-analytics-auth.db")
    client = TestClient(app)

    response = client.get("/api/v1/admin/analytics/trends")

    assert response.status_code == 401
    assert response.json()["detail"] == "admin access token is required"
