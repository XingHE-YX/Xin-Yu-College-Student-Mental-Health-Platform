"""Tests for the deterministic demo dataset used by IMPLEMENTATION_PLAN 14.1."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.constants.account_enums import StudentRiskStatus
from src.constants.treehole_enums import TreeholePublishStatus
from src.constants.workflow_enums import AlertQueueStatus
from src.core.settings import Settings
from src.main import create_app
from src.models import (
    AdminUser,
    AlertCase,
    AuditLog,
    Base,
    PostReaction,
    QuestionBank,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)
from src.services.admin_alert_service import AdminAlertService
from src.services.admin_analytics_service import AdminAnalyticsService
from src.services.admin_audit_log_service import AdminAuditLogService
from src.services.admin_dashboard_service import AdminDashboardService
from src.services.admin_post_service import AdminPostService
from src.services.admin_user_directory_service import AdminUserDirectoryService
from src.services.demo_seed_service import DemoSeedService
from src.utils.seed_demo_dataset import main as seed_demo_dataset_main

FIXED_NOW = datetime(2026, 4, 30, 12, 0, 0)


def build_settings(
    database_file: Path,
    *,
    show_seeded_cases: bool = True,
) -> Settings:
    """Create runtime settings for isolated demo-seed tests."""
    return Settings(
        APP_NAME="心语演示种子数据测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
        SHOW_SEEDED_CASES=show_seeded_cases,
    )


def create_demo_seed_test_app(
    database_file: Path,
    *,
    show_seeded_cases: bool = True,
):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(build_settings(database_file, show_seeded_cases=show_seeded_cases))
    Base.metadata.create_all(app.state.db_engine)
    return app


def create_regular_student_with_token(app) -> str:
    """Insert one non-seeded student row and return a bearer token for feed reads."""
    with app.state.db_session_factory() as session:
        student = StudentUser(
            phone_e164="+8613811111111",
            wechat_openid="wx-runtime-regular-user",
            display_nickname="普通同学",
            display_avatar_seed="seed-regular",
            college_name="普通学院",
            class_name="2026级普通班",
        )
        session.add(student)
        session.commit()
        session.refresh(student)
        return app.state.access_token_service.issue_student_access_token(student)


def test_demo_seed_service_populates_admin_ready_dataset(tmp_path: Path) -> None:
    """The demo seed should populate all admin views with meaningful sample data."""
    app = create_demo_seed_test_app(tmp_path / "demo-seed-ready.db")

    with app.state.db_session_factory() as session:
        summary = DemoSeedService(session, now=FIXED_NOW).seed_demo_dataset()

    assert summary.admin_created is True
    assert summary.students_seeded == 3
    assert summary.questionnaire_submissions_seeded == 8
    assert summary.posts_seeded == 3
    assert summary.reactions_seeded == 3
    assert summary.alerts_seeded == 2
    assert summary.focus_entries_seeded == 2
    assert summary.intervention_logs_seeded == 3
    assert summary.audit_logs_seeded == 4
    assert summary.question_bank_import.seed_files_processed == 5

    with app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AdminUser)) == 1
        assert session.scalar(select(func.count()).select_from(QuestionnaireTemplate)) == 5
        assert session.scalar(select(func.count()).select_from(QuestionBank)) == 74
        assert session.scalar(select(func.count()).select_from(StudentUser)) == 3
        assert session.scalar(select(func.count()).select_from(QuestionnaireSubmission)) == 8
        assert session.scalar(select(func.count()).select_from(TreeholePost)) == 3
        assert session.scalar(select(func.count()).select_from(PostReaction)) == 3
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 2
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 4

        dashboard = AdminDashboardService(session).build_summary()
        assert dashboard.kpis.pending_review_count == 1
        assert dashboard.kpis.confirmed_high_risk_count == 1
        assert dashboard.kpis.focus_student_count == 2
        assert dashboard.kpis.published_post_count == 1
        assert dashboard.stats.blocked_post_count == 1
        assert dashboard.stats.high_risk_student_count == 1
        assert dashboard.stats.questionnaire_submission_count == 8

        alert_snapshot = AdminAlertService(session).list_alert_queue(queue_status=None)
        assert [
            item.queue_status.value for item in alert_snapshot.items
        ] == [
            AlertQueueStatus.PENDING_REVIEW.value,
            AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION.value,
        ]
        assert [item.count for item in alert_snapshot.status_counts] == [1, 1, 0, 0]
        assert alert_snapshot.items[0].source_type == "treehole"
        assert alert_snapshot.items[1].source_type == "assessment"

        post_snapshot = AdminPostService(session).list_posts(publish_status=None)
        assert [
            item.publish_status.value for item in post_snapshot.status_counts
        ] == [
            TreeholePublishStatus.PUBLISHED.value,
            TreeholePublishStatus.HIDDEN_BY_ADMIN.value,
            TreeholePublishStatus.BLOCKED_HIGH_RISK.value,
            TreeholePublishStatus.DELETED_BY_USER.value,
        ]
        assert [item.count for item in post_snapshot.status_counts] == [1, 1, 1, 0]

        user_snapshot = AdminUserDirectoryService(session).list_students(risk_status=None)
        assert [item.risk_status for item in user_snapshot.items] == [
            StudentRiskStatus.HIGH.value,
            StudentRiskStatus.WATCH.value,
            StudentRiskStatus.NORMAL.value,
        ]
        assert [item.count for item in user_snapshot.status_counts] == [1, 1, 1]

        audit_snapshot = AdminAuditLogService(session).list_audit_logs(
            actor_type=None,
            actor_id=None,
            action_code=None,
            target_type=None,
            date_from=None,
            date_to=None,
        )
        assert audit_snapshot.filtered_count == 4
        assert {
            record["action_code"] for record in audit_snapshot.records
        } == {
            "ADMIN_HIDE_POST",
            "ADMIN_CONFIRM_ALERT_CASE",
            "SYSTEM_CREATE_SIMULATED_NOTICE_LOG",
            "ADMIN_ADD_INTERVENTION_NOTE",
        }

        analytics = AdminAnalyticsService(session, now=FIXED_NOW).build_trends_snapshot()
        assert analytics.risk_distribution.total_students == 3
        assert [item.student_count for item in analytics.risk_distribution.items] == [1, 1, 1]
        assert analytics.alert_processing.total_alert_case_count == 2
        assert [item.case_count for item in analytics.alert_processing.items] == [1, 1, 0, 0]
        assert analytics.daily_trends.window_days == 7
        assert analytics.daily_trends.start_date == date(2026, 4, 24)
        assert analytics.daily_trends.end_date == date(2026, 4, 30)
        assert sum(
            item.questionnaire_submission_count for item in analytics.daily_trends.items
        ) == 8
        assert sum(item.treehole_post_count for item in analytics.daily_trends.items) == 3
        assert sum(item.alert_case_count for item in analytics.daily_trends.items) == 2


def test_demo_seed_service_is_idempotent(tmp_path: Path) -> None:
    """Rerunning the demo seed should refresh the dataset instead of duplicating it."""
    app = create_demo_seed_test_app(tmp_path / "demo-seed-idempotent.db")

    with app.state.db_session_factory() as session:
        first_summary = DemoSeedService(session, now=FIXED_NOW).seed_demo_dataset()
    with app.state.db_session_factory() as session:
        second_summary = DemoSeedService(session, now=FIXED_NOW).seed_demo_dataset()

    assert first_summary.admin_created is True
    assert second_summary.admin_created is False

    with app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AdminUser)) == 1
        assert session.scalar(select(func.count()).select_from(StudentUser)) == 3
        assert session.scalar(select(func.count()).select_from(QuestionnaireTemplate)) == 5
        assert session.scalar(select(func.count()).select_from(QuestionBank)) == 74
        assert session.scalar(select(func.count()).select_from(QuestionnaireSubmission)) == 8
        assert session.scalar(select(func.count()).select_from(TreeholePost)) == 3
        assert session.scalar(select(func.count()).select_from(PostReaction)) == 3
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 2
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 4


def test_demo_seed_cli_seeds_database_and_reports_summary(
    tmp_path: Path,
    capsys,
) -> None:
    """The CLI entrypoint should seed the target database and print a usable summary."""
    database_file = tmp_path / "demo-seed-cli.db"
    app = create_demo_seed_test_app(database_file)
    app.state.db_engine.dispose()

    exit_code = seed_demo_dataset_main(
        [
            "--database-url",
            f"sqlite+pysqlite:///{database_file}",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Seeded demo dataset" in captured.out
    assert "Created default admin account" in captured.out
    assert "Question-bank import" in captured.out

    verification_app = create_demo_seed_test_app(database_file)
    with verification_app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(StudentUser)) == 3
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 2
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 4


def test_show_seeded_cases_false_hides_preloaded_demo_data_from_read_apis(
    tmp_path: Path,
) -> None:
    """Seeded demo users, posts, alerts, and audits should disappear when the flag is off."""
    app = create_demo_seed_test_app(
        tmp_path / "demo-seed-hidden.db",
        show_seeded_cases=False,
    )
    with app.state.db_session_factory() as session:
        DemoSeedService(session, now=FIXED_NOW).seed_demo_dataset()

    client = TestClient(app)
    admin_login = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "platform.admin", "password": "Admin#2026"},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["data"]["access_token"]

    dashboard = client.get(
        "/api/v1/admin/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    alerts = client.get(
        "/api/v1/admin/alerts",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    posts = client.get(
        "/api/v1/admin/posts",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    users = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    audit_logs = client.get(
        "/api/v1/admin/audit-logs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    analytics = client.get(
        "/api/v1/admin/analytics/trends",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    student_token = create_regular_student_with_token(app)
    feed = client.get(
        "/api/v1/treehole/feed",
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert dashboard.status_code == 200
    assert dashboard.json()["data"]["summary"]["kpis"] == {
        "pending_review_count": 0,
        "open_high_risk_case_count": 0,
        "confirmed_high_risk_count": 0,
        "focus_student_count": 0,
        "published_post_count": 0,
    }
    assert dashboard.json()["data"]["summary"]["stats"] == {
        "highest_priority_pending_count": 0,
        "blocked_post_count": 0,
        "high_risk_student_count": 0,
        "questionnaire_submission_count": 0,
    }
    assert alerts.status_code == 200
    assert alerts.json()["data"]["items"] == []
    assert [item["count"] for item in alerts.json()["data"]["status_counts"]] == [0, 0, 0, 0]
    assert posts.status_code == 200
    assert posts.json()["data"]["items"] == []
    assert [item["count"] for item in posts.json()["data"]["status_counts"]] == [0, 0, 0, 0]
    assert users.status_code == 200
    assert users.json()["data"]["items"] == []
    assert [item["count"] for item in users.json()["data"]["status_counts"]] == [0, 0, 0]
    assert audit_logs.status_code == 200
    assert audit_logs.json()["data"]["filtered_count"] == 1
    assert audit_logs.json()["data"]["records"][0]["action_code"] == "ADMIN_LOGIN_SUCCESS"
    assert analytics.status_code == 200
    analytics_payload = analytics.json()["data"]["analytics"]
    assert analytics_payload["risk_distribution"]["total_students"] == 0
    assert [item["student_count"] for item in analytics_payload["risk_distribution"]["items"]] == [0, 0, 0]
    assert analytics_payload["alert_processing"]["total_alert_case_count"] == 0
    assert [item["case_count"] for item in analytics_payload["alert_processing"]["items"]] == [0, 0, 0, 0]
    assert feed.status_code == 200
    assert feed.json()["data"]["posts"] == []
