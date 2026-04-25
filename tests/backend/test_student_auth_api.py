"""Tests for student login APIs and session token generation."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from src.constants.account_enums import ConsentStatus, StudentRiskStatus
from src.core.settings import Settings
from src.main import create_app
from src.models import Base, StudentUser
from src.services.wechat_session_service import WeChatSession


def build_settings(
    database_file: Path,
    *,
    enable_demo_login: bool,
) -> Settings:
    """Create runtime settings for isolated student-auth API tests."""
    return Settings(
        APP_NAME="心语认证测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=enable_demo_login,
    )


def create_student_auth_test_app(
    database_file: Path,
    *,
    enable_demo_login: bool,
):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(
        build_settings(database_file, enable_demo_login=enable_demo_login)
    )
    Base.metadata.create_all(app.state.db_engine)
    return app


def test_wechat_login_creates_student_and_returns_access_token(tmp_path) -> None:
    """WeChat login should create a student row and return a signed token."""
    app = create_student_auth_test_app(
        tmp_path / "student-auth-create.db",
        enable_demo_login=False,
    )
    app.state.wechat_session_service.exchange_login_code = lambda code: WeChatSession(
        openid="wx-openid-login-create",
        session_key="session-key-create",
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/student/wechat-login",
        json={
            "login_code": "wx-login-code",
            "phone_ticket": json.dumps(
                {
                    "phone_number": "13812345678",
                    "college_name": "计算机学院",
                    "class_name": "2026级1班",
                }
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["message"] == "success"
    assert payload["request_id"]
    assert payload["data"]["student"]["display_nickname"]
    assert payload["data"]["student"]["college_name"] == "计算机学院"
    assert payload["data"]["student"]["class_name"] == "2026级1班"
    assert payload["data"]["student"]["consent_status"] == "missing"
    assert payload["data"]["student"]["risk_status"] == "normal"
    assert payload["data"]["student"]["is_demo"] is False

    token_payload = app.state.access_token_service.decode_access_token(
        payload["data"]["access_token"],
        expected_role="student",
    )
    assert token_payload["student_id"] == payload["data"]["student"]["id"]
    assert token_payload["is_demo"] is False
    assert token_payload["consent_status"] == "missing"

    with app.state.db_session_factory() as session:
        student = session.scalar(select(StudentUser))
        assert student is not None
        assert student.phone_e164 == "+8613812345678"
        assert student.wechat_openid == "wx-openid-login-create"
        assert student.college_name == "计算机学院"
        assert student.class_name == "2026级1班"
        assert student.consent_status is ConsentStatus.MISSING
        assert student.risk_status is StudentRiskStatus.NORMAL
        assert student.last_login_at is not None


def test_wechat_login_refreshes_existing_student_without_duplication(tmp_path) -> None:
    """Returning WeChat users should refresh one existing student instead of duplicating."""
    app = create_student_auth_test_app(
        tmp_path / "student-auth-refresh.db",
        enable_demo_login=False,
    )
    with app.state.db_session_factory() as session:
        session.add(
            StudentUser(
                phone_e164="+8613812345678",
                wechat_openid=None,
                display_nickname="Quiet Willow",
                display_avatar_seed="seed-willow",
                college_name="待完善学院",
                class_name="待完善班级",
            )
        )
        session.commit()

    app.state.wechat_session_service.exchange_login_code = lambda code: WeChatSession(
        openid="wx-openid-refresh-user",
        session_key="session-key-refresh",
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/student/wechat-login",
        json={
            "login_code": "wx-login-refresh",
            "phone_ticket": json.dumps(
                {
                    "phone_number": "+8613812345678",
                    "college_name": "心理学院",
                    "class_name": "2026级2班",
                }
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["student"]["display_nickname"] == "Quiet Willow"
    assert payload["data"]["student"]["college_name"] == "心理学院"
    assert payload["data"]["student"]["class_name"] == "2026级2班"

    with app.state.db_session_factory() as session:
        students = session.scalars(select(StudentUser)).all()
        assert len(students) == 1
        assert students[0].wechat_openid == "wx-openid-refresh-user"
        assert students[0].college_name == "心理学院"
        assert students[0].class_name == "2026级2班"


def test_wechat_login_returns_conflict_when_phone_and_openid_map_to_different_students(
    tmp_path,
) -> None:
    """Login should fail fast instead of merging two unrelated student identities."""
    app = create_student_auth_test_app(
        tmp_path / "student-auth-conflict.db",
        enable_demo_login=False,
    )
    with app.state.db_session_factory() as session:
        session.add_all(
            [
                StudentUser(
                    phone_e164="+8613812345678",
                    wechat_openid="wx-openid-existing-phone",
                    display_nickname="Quiet Harbor",
                    display_avatar_seed="seed-harbor",
                    college_name="计算机学院",
                    class_name="2026级1班",
                ),
                StudentUser(
                    phone_e164="+8613812345679",
                    wechat_openid="wx-openid-conflicting-openid",
                    display_nickname="Soft Cedar",
                    display_avatar_seed="seed-cedar",
                    college_name="心理学院",
                    class_name="2026级2班",
                ),
            ]
        )
        session.commit()

    app.state.wechat_session_service.exchange_login_code = lambda code: WeChatSession(
        openid="wx-openid-conflicting-openid",
        session_key="session-key-conflict",
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/student/wechat-login",
        json={
            "login_code": "wx-login-conflict",
            "phone_ticket": "13812345678",
        },
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "STUDENT_AUTH_CONFLICT"
    assert "different students" in payload["message"]


def test_demo_login_creates_demo_student_when_enabled(tmp_path) -> None:
    """Demo login should create the fixed demo student only when enabled."""
    app = create_student_auth_test_app(
        tmp_path / "student-auth-demo-enabled.db",
        enable_demo_login=True,
    )
    client = TestClient(app)

    response = client.post("/api/v1/auth/student/demo-login")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["student"]["display_nickname"] == "Quiet Ginkgo"
    assert payload["data"]["student"]["college_name"] == "演示学院"
    assert payload["data"]["student"]["class_name"] == "2026级演示班"
    assert payload["data"]["student"]["is_demo"] is True

    token_payload = app.state.access_token_service.decode_access_token(
        payload["data"]["access_token"],
        expected_role="student",
    )
    assert token_payload["is_demo"] is True

    with app.state.db_session_factory() as session:
        students = session.scalars(select(StudentUser)).all()
        assert len(students) == 1
        assert students[0].is_demo is True
        assert students[0].phone_e164 == "+8613900000001"
        assert students[0].wechat_openid == "demo-student-openid"


def test_demo_login_is_blocked_when_disabled(tmp_path) -> None:
    """Demo login should not be available unless the env switch is enabled."""
    app = create_student_auth_test_app(
        tmp_path / "student-auth-demo-disabled.db",
        enable_demo_login=False,
    )
    client = TestClient(app)

    response = client.post("/api/v1/auth/student/demo-login")

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "DEMO_LOGIN_DISABLED"
    assert payload["request_id"]
