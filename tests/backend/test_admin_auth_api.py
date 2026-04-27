"""Tests for administrator login APIs and Streamlit-facing JWT sessions."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import func, select

from src.constants.account_enums import AdminRoleCode
from src.constants.workflow_enums import AuditActorType
from src.core.settings import Settings
from src.main import create_app
from src.models import AdminUser, AuditLog, Base

PASSWORD_HASHER = PasswordHash.recommended()


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated admin-auth API tests."""
    return Settings(
        APP_NAME="心语管理员认证测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_admin_auth_test_app(database_file: Path):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(build_settings(database_file))
    Base.metadata.create_all(app.state.db_engine)
    return app


def create_admin_user(
    app,
    *,
    username: str = "platform.admin",
    password: str = "Admin#2026",
    is_active: bool = True,
) -> AdminUser:
    """Insert one administrator row with a real Argon2 password hash."""
    with app.state.db_session_factory() as session:
        admin = AdminUser(
            username=username,
            password_hash=PASSWORD_HASHER.hash(password),
            role_code=AdminRoleCode.PLATFORM_ADMIN,
            display_name="平台管理员",
            is_active=is_active,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        return admin


def test_admin_login_returns_access_token_and_audits_success(tmp_path) -> None:
    """Successful admin login should issue a JWT, refresh last_login_at, and audit success."""
    app = create_admin_auth_test_app(tmp_path / "admin-auth-success.db")
    admin = create_admin_user(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": admin.username, "password": "Admin#2026"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["message"] == "success"
    assert payload["data"]["admin"]["username"] == admin.username
    assert payload["data"]["admin"]["display_name"] == "平台管理员"
    assert payload["data"]["admin"]["role_code"] == "platform_admin"
    assert payload["data"]["admin"]["is_active"] is True
    assert payload["data"]["admin"]["last_login_at"] is not None

    token_payload = app.state.access_token_service.decode_access_token(
        payload["data"]["access_token"],
        expected_role="admin",
    )
    assert token_payload["admin_id"] == admin.id
    assert token_payload["username"] == admin.username
    assert token_payload["role_code"] == "platform_admin"

    with app.state.db_session_factory() as session:
        refreshed_admin = session.get(AdminUser, admin.id)
        assert refreshed_admin is not None
        assert refreshed_admin.last_login_at is not None

        audit_log = session.scalar(select(AuditLog))
        assert audit_log is not None
        assert audit_log.actor_type is AuditActorType.ADMIN
        assert audit_log.actor_id == admin.id
        assert audit_log.action_code == "ADMIN_LOGIN_SUCCESS"
        assert audit_log.target_type == "admin_user"
        assert audit_log.target_id == admin.id
        assert audit_log.metadata_json == {
            "role_code": "platform_admin",
            "username": admin.username,
        }


def test_admin_login_rejects_invalid_credentials(tmp_path) -> None:
    """Wrong admin credentials should return a business 401 error without auditing."""
    app = create_admin_auth_test_app(tmp_path / "admin-auth-invalid.db")
    admin = create_admin_user(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": admin.username, "password": "wrong-password"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "ADMIN_AUTH_INVALID_CREDENTIALS"
    assert "incorrect" in payload["message"]

    with app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_admin_login_rejects_inactive_account(tmp_path) -> None:
    """Inactive administrators should be denied access even with a correct password."""
    app = create_admin_auth_test_app(tmp_path / "admin-auth-inactive.db")
    admin = create_admin_user(app, is_active=False)
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": admin.username, "password": "Admin#2026"},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "ADMIN_ACCOUNT_INACTIVE"
    assert "inactive" in payload["message"]


def test_admin_me_returns_current_profile_for_valid_token(tmp_path) -> None:
    """The authenticated admin profile endpoint should return the current account data."""
    app = create_admin_auth_test_app(tmp_path / "admin-auth-me.db")
    admin = create_admin_user(app)
    client = TestClient(app)

    login_response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": admin.username, "password": "Admin#2026"},
    )
    access_token = login_response.json()["data"]["access_token"]

    response = client.get(
        "/api/v1/admin/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["admin"]["id"] == admin.id
    assert payload["data"]["admin"]["username"] == admin.username
    assert payload["data"]["admin"]["role_code"] == "platform_admin"


def test_admin_me_requires_bearer_token(tmp_path) -> None:
    """Current-admin queries should reject unauthenticated requests."""
    app = create_admin_auth_test_app(tmp_path / "admin-auth-me-auth.db")
    client = TestClient(app)

    response = client.get("/api/v1/admin/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "admin access token is required"
