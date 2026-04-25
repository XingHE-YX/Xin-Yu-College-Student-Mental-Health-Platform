"""Tests for questionnaire metadata and required-progress APIs."""

from __future__ import annotations

from datetime import datetime, timedelta
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
    """Create runtime settings for isolated questionnaire API tests."""
    return Settings(
        APP_NAME="心语问卷 API 测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_questionnaire_api_test_app(database_file: Path):
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
            wechat_openid="wx-questionnaire-student",
            display_nickname="Quiet Harbor",
            display_avatar_seed="seed-harbor",
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
    standardized_score: int | None,
    risk_level: QuestionnaireRiskLevel,
    hard_trigger_hit: bool = False,
) -> QuestionnaireSubmission:
    """Create one questionnaire submission row for progress and list tests."""
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
            started_at=submitted_at - timedelta(minutes=6),
            submitted_at=submitted_at,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=raw_score,
            standardized_score=standardized_score,
            risk_level=risk_level,
            hard_trigger_hit=hard_trigger_hit,
            scoring_snapshot_json={"questionnaire_code": questionnaire_code},
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)
        return submission


def test_list_questionnaires_returns_catalog_in_app_flow_order(tmp_path) -> None:
    """Questionnaire list should expose all active questionnaires in flow order."""
    app = create_questionnaire_api_test_app(tmp_path / "questionnaire-list.db")
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.get(
        "/api/v1/questionnaires",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    questionnaires = payload["data"]["questionnaires"]
    assert [item["code"] for item in questionnaires] == [
        "SCREEN",
        "SDS",
        "SAS",
        "SLEEP",
        "UPI",
    ]
    assert questionnaires[0]["name"] == "快速筛查"
    assert questionnaires[0]["question_count"] == 15
    assert questionnaires[0]["flow_step"] == "S05"
    assert questionnaires[0]["latest_submission"] is None
    assert questionnaires[-1]["category"] == "optional"
    assert questionnaires[-1]["unlock_required"] is False


def test_questionnaire_detail_returns_renderable_questions_without_scoring_metadata(
    tmp_path,
) -> None:
    """Questionnaire detail should expose render metadata but keep scoring internals private."""
    app = create_questionnaire_api_test_app(tmp_path / "questionnaire-detail.db")
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.get(
        "/api/v1/questionnaires/screen",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    questionnaire = response.json()["data"]["questionnaire"]
    assert questionnaire["code"] == "SCREEN"
    assert questionnaire["flow_step"] == "S05"
    assert questionnaire["question_count"] == 15
    assert len(questionnaire["questions"]) == 15

    first_question = questionnaire["questions"][0]
    assert first_question["question_code"] == "SCREEN_01"
    assert first_question["question_order"] == 1
    assert first_question["question_type"] == "single_choice"
    assert first_question["options"][0] == {"value": "1", "label": "从不"}
    assert "score_mapping" not in first_question
    assert "hard_trigger_rule" not in first_question
    assert questionnaire["latest_submission"] is None


def test_progress_counts_latest_required_submissions_without_double_counting(
    tmp_path,
) -> None:
    """Required progress should count each questionnaire once using the latest submission."""
    app = create_questionnaire_api_test_app(tmp_path / "questionnaire-progress.db")
    student, token = create_student_with_token(app)
    older_submission = create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SCREEN",
        submitted_at=datetime(2026, 4, 20, 9, 0, 0),
        raw_score=41,
        standardized_score=None,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    latest_screen_submission = create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SCREEN",
        submitted_at=datetime(2026, 4, 20, 10, 0, 0),
        raw_score=53,
        standardized_score=None,
        risk_level=QuestionnaireRiskLevel.WATCH,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="SDS",
        submitted_at=datetime(2026, 4, 21, 8, 30, 0),
        raw_score=42,
        standardized_score=52,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="UPI",
        submitted_at=datetime(2026, 4, 22, 18, 0, 0),
        raw_score=1,
        standardized_score=None,
        risk_level=QuestionnaireRiskLevel.HIGH,
        hard_trigger_hit=True,
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/questionnaires/progress",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    progress = response.json()["data"]["progress"]
    assert progress["completed_required_questionnaires"] == 2
    assert progress["total_required_questionnaires"] == 4
    assert progress["completed_required_questions"] == 35
    assert progress["total_required_questions"] == 70
    assert progress["full_profile_unlocked"] is False

    required_by_code = {
        entry["code"]: entry for entry in progress["required_questionnaires"]
    }
    assert required_by_code["SCREEN"]["completed"] is True
    assert required_by_code["SCREEN"]["latest_submission"]["submission_id"] == (
        latest_screen_submission.id
    )
    assert required_by_code["SCREEN"]["latest_submission"]["raw_score"] == 53
    assert required_by_code["SDS"]["completed"] is True
    assert required_by_code["SAS"]["completed"] is False
    assert required_by_code["SLEEP"]["completed"] is False
    assert older_submission.id != latest_screen_submission.id


def test_list_questionnaires_includes_latest_submission_summary(tmp_path) -> None:
    """Questionnaire list should surface the latest student result when it exists."""
    app = create_questionnaire_api_test_app(tmp_path / "questionnaire-list-result.db")
    student, token = create_student_with_token(app)
    create_submission(
        app,
        student_id=student.id,
        questionnaire_code="UPI",
        submitted_at=datetime(2026, 4, 24, 12, 0, 0),
        raw_score=1,
        standardized_score=None,
        risk_level=QuestionnaireRiskLevel.HIGH,
        hard_trigger_hit=True,
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/questionnaires",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    questionnaires = response.json()["data"]["questionnaires"]
    upi_entry = next(item for item in questionnaires if item["code"] == "UPI")
    assert upi_entry["latest_submission"]["risk_level"] == "high"
    assert upi_entry["latest_submission"]["hard_trigger_hit"] is True
    assert upi_entry["latest_submission"]["raw_score"] == 1


def test_questionnaire_detail_returns_not_found_for_unknown_code(tmp_path) -> None:
    """Questionnaire detail should fail with a business error for unknown codes."""
    app = create_questionnaire_api_test_app(tmp_path / "questionnaire-missing.db")
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.get(
        "/api/v1/questionnaires/unknown",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "QUESTIONNAIRE_NOT_FOUND"
    assert "UNKNOWN" in payload["message"]


def test_questionnaire_routes_require_student_authentication(tmp_path) -> None:
    """Questionnaire metadata endpoints should reject unauthenticated access."""
    app = create_questionnaire_api_test_app(tmp_path / "questionnaire-auth.db")
    client = TestClient(app)

    response = client.get("/api/v1/questionnaires")

    assert response.status_code == 401
    assert response.json()["detail"] == "student access token is required"
