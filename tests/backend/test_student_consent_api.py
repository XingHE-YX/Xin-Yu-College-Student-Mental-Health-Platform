"""Tests for student consent submission APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from src.constants.account_enums import ConsentStatus, ConsentType
from src.core.settings import Settings
from src.main import create_app
from src.models import Base, ConsentRecord, StudentUser


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated student-consent API tests."""
    return Settings(
        APP_NAME="心语授权测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_student_consent_test_app(database_file: Path):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(build_settings(database_file))
    Base.metadata.create_all(app.state.db_engine)
    return app


def create_student_with_token(
    app,
    *,
    consent_status: ConsentStatus = ConsentStatus.MISSING,
) -> tuple[StudentUser, str]:
    """Create one student row and issue an access token for API tests."""
    with app.state.db_session_factory() as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-consent-student",
            display_nickname="Quiet Harbor",
            display_avatar_seed="seed-harbor",
            college_name="计算机学院",
            class_name="2026级1班",
            consent_status=consent_status,
        )
        session.add(student)
        session.commit()
        session.refresh(student)
        token = app.state.access_token_service.issue_student_access_token(student)
        return student, token


def test_submit_crisis_consent_updates_student_status_and_returns_fresh_token(
    tmp_path,
) -> None:
    """Crisis consent submission should update `student_users.consent_status`."""
    app = create_student_consent_test_app(tmp_path / "student-consent-granted.db")
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/consents",
        json={
            "consent_type": "crisis_intervention_authorization",
            "consent_version": "v1.0",
            "granted": True,
        },
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "pytest-consent-client",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["student"]["consent_status"] == "granted"
    assert payload["data"]["consent_record"]["consent_type"] == (
        "crisis_intervention_authorization"
    )
    assert payload["data"]["consent_record"]["granted"] is True

    refreshed_token_payload = app.state.access_token_service.decode_access_token(
        payload["data"]["access_token"],
        expected_role="student",
    )
    assert refreshed_token_payload["consent_status"] == "granted"

    with app.state.db_session_factory() as session:
        student = session.scalar(select(StudentUser))
        record = session.scalar(select(ConsentRecord))
        assert student is not None
        assert record is not None
        assert student.consent_status is ConsentStatus.GRANTED
        assert record.consent_type is ConsentType.CRISIS_INTERVENTION_AUTHORIZATION
        assert record.granted is True
        assert record.user_agent == "pytest-consent-client"
        assert record.ip_address == "testclient"


def test_submit_declined_crisis_consent_appends_history_and_sets_declined_status(
    tmp_path,
) -> None:
    """Repeated crisis decisions should append records while keeping the latest status."""
    app = create_student_consent_test_app(tmp_path / "student-consent-history.db")
    _, token = create_student_with_token(app)
    client = TestClient(app)

    first_response = client.post(
        "/api/v1/consents",
        json={
            "consent_type": "crisis_intervention_authorization",
            "consent_version": "v1.0",
            "granted": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/api/v1/consents",
        json={
            "consent_type": "crisis_intervention_authorization",
            "consent_version": "v1.1",
            "granted": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert second_response.status_code == 200
    payload = second_response.json()
    assert payload["data"]["student"]["consent_status"] == "declined"
    assert payload["data"]["consent_record"]["consent_version"] == "v1.1"
    assert payload["data"]["consent_record"]["granted"] is False

    with app.state.db_session_factory() as session:
        records = session.scalars(select(ConsentRecord).order_by(ConsentRecord.id)).all()
        student = session.scalar(select(StudentUser))
        assert student is not None
        assert student.consent_status is ConsentStatus.DECLINED
        assert len(records) == 2
        assert [record.consent_version for record in records] == ["v1.0", "v1.1"]
        assert [record.granted for record in records] == [True, False]


def test_submit_privacy_policy_does_not_change_crisis_consent_status(tmp_path) -> None:
    """Privacy consent should be traceable without altering crisis auth state."""
    app = create_student_consent_test_app(tmp_path / "student-consent-privacy.db")
    _, token = create_student_with_token(app, consent_status=ConsentStatus.GRANTED)
    client = TestClient(app)

    response = client.post(
        "/api/v1/consents",
        json={
            "consent_type": "privacy_policy",
            "consent_version": "v2.0",
            "granted": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["student"]["consent_status"] == "granted"
    assert payload["data"]["consent_record"]["consent_type"] == "privacy_policy"

    refreshed_token_payload = app.state.access_token_service.decode_access_token(
        payload["data"]["access_token"],
        expected_role="student",
    )
    assert refreshed_token_payload["consent_status"] == "granted"

    with app.state.db_session_factory() as session:
        student = session.scalar(select(StudentUser))
        record = session.scalar(select(ConsentRecord))
        assert student is not None
        assert record is not None
        assert student.consent_status is ConsentStatus.GRANTED
        assert record.consent_type is ConsentType.PRIVACY_POLICY


def test_submit_consent_requires_student_authentication(tmp_path) -> None:
    """Student consent submission should reject unauthenticated requests."""
    app = create_student_consent_test_app(tmp_path / "student-consent-auth.db")
    client = TestClient(app)

    response = client.post(
        "/api/v1/consents",
        json={
            "consent_type": "crisis_intervention_authorization",
            "consent_version": "v1.0",
            "granted": True,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "student access token is required"
