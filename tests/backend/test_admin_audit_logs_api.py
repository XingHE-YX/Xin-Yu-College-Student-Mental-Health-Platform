"""Tests for administrator audit-log APIs."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from src.constants.account_enums import AdminRoleCode, ConsentStatus, StudentRiskStatus
from src.constants.workflow_enums import AuditActorType
from src.core.settings import Settings
from src.main import create_app
from src.models import AdminUser, AuditLog, Base, StudentUser

PASSWORD_HASHER = PasswordHash.recommended()


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated admin-audit API tests."""
    return Settings(
        APP_NAME="心语后台审计日志测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_admin_audit_test_app(database_file: Path):
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


def seed_audit_log_data(app) -> dict[str, int]:
    """Insert students and baseline audit events for A07 filter tests."""
    with app.state.db_session_factory() as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-audit-user-1",
            display_nickname="Quiet Harbor",
            display_avatar_seed="seed-harbor",
            college_name="心理学院",
            class_name="2026级1班",
            consent_status=ConsentStatus.GRANTED,
            risk_status=StudentRiskStatus.HIGH,
        )
        session.add(student)
        session.flush()

        session.add_all(
            [
                AuditLog(
                    actor_type=AuditActorType.ADMIN,
                    actor_id=1,
                    action_code="ADMIN_LOGIN_SUCCESS",
                    target_type="admin_user",
                    target_id=1,
                    metadata_json={"username": "platform.admin"},
                    ip_address="127.0.0.1",
                    created_at=datetime(2026, 4, 26, 8, 0, 0),
                ),
                AuditLog(
                    actor_type=AuditActorType.SYSTEM,
                    actor_id=None,
                    action_code="SYSTEM_CREATE_SIMULATED_NOTICE_LOG",
                    target_type="alert_case",
                    target_id=7,
                    metadata_json={"queue_status": "confirmed_pending_intervention"},
                    ip_address=None,
                    created_at=datetime(2026, 4, 27, 9, 30, 0),
                ),
            ]
        )
        session.commit()
        return {"student_id": student.id}


def login_admin(client: TestClient) -> str:
    """Authenticate the seeded administrator and return the bearer token."""
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "platform.admin", "password": "Admin#2026"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_audit_logs_filter_by_target_and_action_after_user_sensitive_actions(tmp_path) -> None:
    """A07 should surface new user-detail and phone-reveal audits under filters."""
    app = create_admin_audit_test_app(tmp_path / "admin-audit-logs.db")
    create_admin_user(app)
    identifiers = seed_audit_log_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    detail_response = client.get(
        f"/api/v1/admin/users/{identifiers['student_id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert detail_response.status_code == 200

    reveal_response = client.post(
        f"/api/v1/admin/users/{identifiers['student_id']}/reveal-phone",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert reveal_response.status_code == 200

    response = client.get(
        "/api/v1/admin/audit-logs",
        params={
            "actor_type": "admin",
            "action_code": "ADMIN_REVEAL_STUDENT_PHONE",
            "target_type": "student_user",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["filtered_count"] == 1
    record = payload["data"]["records"][0]
    assert record["action_code"] == "ADMIN_REVEAL_STUDENT_PHONE"
    assert record["target_type"] == "student_user"
    assert record["target_label"].startswith("STU-")
    assert record["actor_label"] == "平台管理员 / platform.admin"
    assert "完整手机号" in record["summary_text"]


def test_audit_logs_return_actor_options_and_date_range_filter(tmp_path) -> None:
    """A07 should expose actor filter options and respect the requested date range."""
    app = create_admin_audit_test_app(tmp_path / "admin-audit-log-filters.db")
    create_admin_user(app)
    seed_audit_log_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        "/api/v1/admin/audit-logs",
        params={
            "date_from": date(2026, 4, 27).isoformat(),
            "date_to": date(2026, 4, 27).isoformat(),
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["filtered_count"] == 1
    assert payload["records"][0]["action_code"] == "SYSTEM_CREATE_SIMULATED_NOTICE_LOG"
    actor_options = payload["actor_options"]
    assert {"actor_type": "admin", "actor_id": 1, "label": "平台管理员 / platform.admin"} in actor_options
    assert {"actor_type": "system", "actor_id": None, "label": "系统"} in actor_options
    assert "admin_user" in payload["target_type_options"]
    assert "alert_case" in payload["target_type_options"]
