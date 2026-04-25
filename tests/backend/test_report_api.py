"""Tests for student report APIs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.constants.account_enums import ConsentStatus
from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionnaireSubmissionStatus,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import Base, QuestionnaireSubmission, QuestionnaireTemplate, StudentUser

QUESTIONNAIRE_TEMPLATE_FIXTURES = (
    (
        "SCREEN",
        "快速筛查",
        QuestionnaireCategory.REQUIRED,
        15,
        QuestionnaireScoringMode.SUM_1_5,
        True,
    ),
    (
        "SDS",
        "SDS 抑郁自评量表",
        QuestionnaireCategory.REQUIRED,
        20,
        QuestionnaireScoringMode.ZUNG_STANDARD,
        True,
    ),
    (
        "SAS",
        "SAS 焦虑自评量表",
        QuestionnaireCategory.REQUIRED,
        20,
        QuestionnaireScoringMode.ZUNG_STANDARD,
        True,
    ),
    (
        "SLEEP",
        "睡眠问卷",
        QuestionnaireCategory.REQUIRED,
        15,
        QuestionnaireScoringMode.SUM_0_3,
        True,
    ),
    (
        "UPI",
        "UPI 辅助筛查",
        QuestionnaireCategory.OPTIONAL,
        4,
        QuestionnaireScoringMode.YES_NO,
        False,
    ),
)


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated report API tests."""
    return Settings(
        APP_NAME="心语报告 API 测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_report_api_test_app(database_file: Path):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(build_settings(database_file))
    Base.metadata.create_all(app.state.db_engine)

    with app.state.db_session_factory() as session:
        for (
            code,
            name,
            category,
            question_count,
            scoring_mode,
            unlock_required,
        ) in QUESTIONNAIRE_TEMPLATE_FIXTURES:
            session.add(
                QuestionnaireTemplate(
                    code=code,
                    name=name,
                    category=category,
                    question_count=question_count,
                    scoring_mode=scoring_mode,
                    unlock_required=unlock_required,
                    is_active=True,
                )
            )
        session.commit()
    return app


def create_student_with_token(app) -> tuple[StudentUser, str]:
    """Create one student row and issue an access token for API tests."""
    with app.state.db_session_factory() as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-report-student",
            display_nickname="Quiet Harbor",
            display_avatar_seed="seed-report",
            college_name="计算机学院",
            class_name="2026级1班",
            consent_status=ConsentStatus.GRANTED,
        )
        session.add(student)
        session.commit()
        session.refresh(student)
        token = app.state.access_token_service.issue_student_access_token(student)
        return student, token


def create_submission(
    app,
    *,
    student_id: int,
    questionnaire_code: str,
    submitted_at: datetime,
    raw_score: int,
    risk_level: QuestionnaireRiskLevel,
    standardized_score: int | None = None,
    hard_trigger_hit: bool = False,
) -> QuestionnaireSubmission:
    """Create one questionnaire submission row for report API tests."""
    with app.state.db_session_factory() as session:
        template = session.scalar(
            select(QuestionnaireTemplate).where(
                QuestionnaireTemplate.code == questionnaire_code
            )
        )
        assert template is not None

        submission = QuestionnaireSubmission(
            student_id=student_id,
            template_id=template.id,
            started_at=submitted_at - timedelta(minutes=5),
            submitted_at=submitted_at,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=raw_score,
            standardized_score=standardized_score,
            risk_level=risk_level,
            hard_trigger_hit=hard_trigger_hit,
            scoring_snapshot_json={
                "questionnaire_code": questionnaire_code,
                "hard_trigger_matches": (
                    [
                        {
                            "question_code": f"{questionnaire_code}_TRIGGER",
                            "reason_code": "HT-API",
                            "operator": "==",
                            "expected_value": "yes",
                            "matched_value": "yes",
                        }
                    ]
                    if hard_trigger_hit
                    else []
                ),
            },
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)
        return submission


def test_report_summary_returns_locked_state_without_submissions(tmp_path) -> None:
    """Students with no questionnaire records should still get a locked summary payload."""
    app = create_report_api_test_app(tmp_path / "report-summary-locked.db")
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.get(
        "/api/v1/reports/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    summary = response.json()["data"]["summary"]
    assert summary["state"] == "locked"
    assert summary["progress"]["required_questions_completed"] == 0
    assert summary["progress"]["required_questions_total"] == 70
    assert summary["next_actions"][0]["target_questionnaire_code"] == "SCREEN"
    assert summary["scale_results"] == []


def test_report_summary_returns_partial_results_and_history(tmp_path) -> None:
    """Partial report summaries should expose current scale results and history entries."""
    app = create_report_api_test_app(tmp_path / "report-summary-partial.db")
    student, token = create_student_with_token(app)
    now = datetime.now(UTC).replace(tzinfo=None)
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SCREEN",
        submitted_at=now,
        raw_score=44,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SDS",
        submitted_at=now + timedelta(minutes=5),
        raw_score=43,
        standardized_score=53,
        risk_level=QuestionnaireRiskLevel.WATCH,
    )
    client = TestClient(app)

    summary_response = client.get(
        "/api/v1/reports/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    history_response = client.get(
        "/api/v1/reports/history",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]["summary"]
    assert summary["state"] == "partial"
    assert summary["overview_badge"]["risk_level"] == "watch"
    assert summary["progress"]["required_questions_completed"] == 35
    assert [item["questionnaire"]["code"] for item in summary["scale_results"]] == [
        "SCREEN",
        "SDS",
    ]

    assert history_response.status_code == 200
    records = history_response.json()["data"]["records"]
    assert [record["questionnaire_code"] for record in records] == ["SDS", "SCREEN"]
    assert records[0]["risk_level"] == "watch"
    assert records[0]["score_summary"][1]["value"] == 53


def test_full_report_returns_conflict_until_required_chain_is_complete(tmp_path) -> None:
    """Full report should stay locked until all four required questionnaires exist."""
    app = create_report_api_test_app(tmp_path / "report-full-locked.db")
    student, token = create_student_with_token(app)
    now = datetime.now(UTC).replace(tzinfo=None)
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SCREEN",
        submitted_at=now,
        raw_score=44,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SDS",
        submitted_at=now + timedelta(minutes=1),
        raw_score=42,
        standardized_score=52,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SAS",
        submitted_at=now + timedelta(minutes=2),
        raw_score=39,
        standardized_score=48,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/reports/full",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "FULL_PROFILE_LOCKED"
    assert "missing: SLEEP" in payload["message"]


def test_full_report_returns_unlocked_payload_after_all_required_submissions(
    tmp_path,
) -> None:
    """Full report should be returned once the fixed 70-question chain is complete."""
    app = create_report_api_test_app(tmp_path / "report-full-unlocked.db")
    student, token = create_student_with_token(app)
    now = datetime.now(UTC).replace(tzinfo=None)
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SCREEN",
        submitted_at=now,
        raw_score=44,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SDS",
        submitted_at=now + timedelta(minutes=1),
        raw_score=42,
        standardized_score=52,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SAS",
        submitted_at=now + timedelta(minutes=2),
        raw_score=39,
        standardized_score=48,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SLEEP",
        submitted_at=now + timedelta(minutes=3),
        raw_score=6,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="UPI",
        submitted_at=now + timedelta(minutes=4),
        raw_score=1,
        risk_level=QuestionnaireRiskLevel.HIGH,
        hard_trigger_hit=True,
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/reports/full",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    report = response.json()["data"]["report"]
    assert report["report_type"] == "full_profile"
    assert report["risk_level"] == "high"
    assert report["source_submission_ids"] == [1, 2, 3, 4, 5]
    assert report["content"]["unlock_status"]["full_profile_unlocked"] is True
    assert report["content"]["result_badge"]["risk_level"] == "high"
    assert report["content"]["questionnaire_summaries"][-1]["questionnaire"]["code"] == "UPI"


def test_report_routes_require_student_authentication(tmp_path) -> None:
    """Report APIs should reject unauthenticated requests."""
    app = create_report_api_test_app(tmp_path / "report-auth.db")
    client = TestClient(app)

    response = client.get("/api/v1/reports/summary")

    assert response.status_code == 401
    assert response.json()["detail"] == "student access token is required"
