"""Tests for questionnaire submission APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.constants.account_enums import ConsentStatus, StudentRiskStatus
from src.constants.questionnaire_enums import (
    QuestionnaireRiskLevel,
    QuestionnaireSubmissionStatus,
)
from src.constants.workflow_enums import (
    AlertQueueStatus,
    CaseSourceType,
    FocusListStatus,
    ReviewPriority,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import (
    AlertCase,
    Base,
    FocusListEntry,
    QuestionBank,
    QuestionnaireAnswer,
    QuestionnaireSubmission,
    StudentUser,
)
from src.services.question_bank_seed_service import QuestionBankSeedService
from src.utils.validate_question_bank_seeds import load_seed_file

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTION_BANK_DIR = REPO_ROOT / "appendices" / "question_bank"
SEED_FILE_BY_CODE = {
    "SCREEN": "screen_questions.json",
    "SDS": "sds_questions.json",
    "SAS": "sas_questions.json",
    "SLEEP": "sleep_questions.json",
    "UPI": "upi_questions.json",
}


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated questionnaire submission API tests."""
    return Settings(
        APP_NAME="心语问卷提交测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_questionnaire_submission_test_app(
    database_file: Path,
    *,
    import_question_bank: bool,
):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(build_settings(database_file))
    Base.metadata.create_all(app.state.db_engine)

    if import_question_bank:
        seed_paths = sorted(QUESTION_BANK_DIR.glob("*_questions.json"))
        with app.state.db_session_factory() as session:
            QuestionBankSeedService(session).import_seed_files(seed_paths)
    return app


def create_student_with_token(
    app,
    *,
    risk_status: StudentRiskStatus = StudentRiskStatus.NORMAL,
) -> tuple[StudentUser, str]:
    """Create one student row and issue an access token for API tests."""
    with app.state.db_session_factory() as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-questionnaire-submit-student",
            display_nickname="Quiet Harbor",
            display_avatar_seed="seed-harbor",
            college_name="计算机学院",
            class_name="2026级1班",
            consent_status=ConsentStatus.GRANTED,
            risk_status=risk_status,
        )
        session.add(student)
        session.commit()
        session.refresh(student)
        token = app.state.access_token_service.issue_student_access_token(student)
        return student, token


def load_seed(questionnaire_code: str):
    """Load one committed questionnaire seed file by questionnaire code."""
    return load_seed_file(QUESTION_BANK_DIR / SEED_FILE_BY_CODE[questionnaire_code])


def matches_hard_trigger(question_seed, raw_value: str) -> bool:
    """Return whether one raw answer value would hit the question hard trigger."""
    rule = question_seed.hard_trigger_rule
    if rule is None:
        return False

    if question_seed.question_type.value == "yes_no":
        return rule.operator == "==" and raw_value == rule.value

    mapped_score = question_seed.score_mapping[raw_value]
    if rule.operator == ">=":
        return mapped_score >= rule.value
    if isinstance(rule.value, int):
        return mapped_score == rule.value
    return raw_value == rule.value


def build_low_risk_answers(questionnaire_code: str) -> dict[str, str]:
    """Build a full answer mapping that avoids hard triggers and minimizes risk."""
    seed_file = load_seed(questionnaire_code)
    answers: dict[str, str] = {}
    for question_seed in seed_file.questions:
        scored_options: list[tuple[int, str]] = []
        for raw_value, mapped_score in question_seed.score_mapping.items():
            if matches_hard_trigger(question_seed, raw_value):
                continue
            normalized_score = (
                5 - mapped_score if question_seed.reverse_scored else mapped_score
            )
            scored_options.append((normalized_score, raw_value))

        if not scored_options:
            raise AssertionError(
                f"no non-trigger scoring options for {question_seed.question_id}"
            )

        answers[question_seed.question_id] = min(scored_options)[1]
    return answers


def build_uniform_answers(questionnaire_code: str, selected_option: str) -> dict[str, str]:
    """Build an answer mapping that reuses the same raw option for every question."""
    seed_file = load_seed(questionnaire_code)
    return {
        question_seed.question_id: selected_option
        for question_seed in seed_file.questions
    }


def build_request_payload(answers: dict[str, str], *, reverse_order: bool = False) -> dict:
    """Build the API request payload from a question-code mapping."""
    items = [
        {
            "question_code": question_code,
            "selected_option": selected_option,
        }
        for question_code, selected_option in answers.items()
    ]
    if reverse_order:
        items = list(reversed(items))
    return {"answers": items}


def count_rows(session, model) -> int:
    """Return the current row count for one ORM model."""
    return session.scalar(select(func.count()).select_from(model)) or 0


def load_submission_with_answers(session, submission_id: int) -> QuestionnaireSubmission:
    """Load one questionnaire submission with answer and question relationships."""
    submission = session.scalar(
        select(QuestionnaireSubmission)
        .options(
            selectinload(QuestionnaireSubmission.answers).selectinload(
                QuestionnaireAnswer.question
            )
        )
        .where(QuestionnaireSubmission.id == submission_id)
    )
    assert submission is not None
    return submission


def test_submit_screen_persists_submission_and_answers(tmp_path) -> None:
    """SCREEN submissions should be scored, stored, and linked to question rows."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-screen.db",
        import_question_bank=True,
    )
    student, token = create_student_with_token(app)
    client = TestClient(app)
    answers = build_low_risk_answers("SCREEN")

    response = client.post(
        "/api/v1/questionnaires/screen/submissions",
        json=build_request_payload(answers, reverse_order=True),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["questionnaire_code"] == "SCREEN"
    assert payload["data"]["standardized_score"] is None
    assert payload["data"]["risk_level"] == "low"
    assert payload["data"]["hard_trigger_hit"] is False

    with app.state.db_session_factory() as session:
        submission = load_submission_with_answers(session, payload["data"]["submission_id"])
        assert submission.student_id == student.id
        assert submission.status is QuestionnaireSubmissionStatus.SCORED
        assert submission.raw_score == payload["data"]["raw_score"]
        assert submission.standardized_score is None
        assert submission.risk_level is QuestionnaireRiskLevel.LOW
        assert submission.hard_trigger_hit is False
        assert submission.scoring_snapshot_json["questionnaire_code"] == "SCREEN"
        assert len(submission.answers) == 15
        assert {
            answer.question.question_code for answer in submission.answers
        } == set(answers)
        assert count_rows(session, AlertCase) == 0
        refreshed_student = session.get(StudentUser, student.id)
        assert refreshed_student is not None
        assert refreshed_student.risk_status is StudentRiskStatus.NORMAL


def test_submit_sds_and_sas_return_standardized_scores(tmp_path) -> None:
    """Zung questionnaires should persist standardized scores after submission."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-zung.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    for questionnaire_code in ("SDS", "SAS"):
        response = client.post(
            f"/api/v1/questionnaires/{questionnaire_code.lower()}/submissions",
            json=build_request_payload(build_low_risk_answers(questionnaire_code)),
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["questionnaire_code"] == questionnaire_code
        assert isinstance(payload["standardized_score"], int)
        assert payload["risk_level"] == "low"


def test_submit_sleep_and_upi_both_persist_valid_results(tmp_path) -> None:
    """SLEEP and UPI submissions should both persist and return effective results."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-sleep-upi.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    for questionnaire_code in ("SLEEP", "UPI"):
        response = client.post(
            f"/api/v1/questionnaires/{questionnaire_code.lower()}/submissions",
            json=build_request_payload(build_low_risk_answers(questionnaire_code)),
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["questionnaire_code"] == questionnaire_code
        assert payload["standardized_score"] is None
        assert payload["hard_trigger_hit"] is False


def test_submit_sds_watch_result_writes_focus_list_entry(tmp_path) -> None:
    """Watch-level SDS submissions should enter the focus list without creating alert cases."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-sds-watch.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/questionnaires/sds/submissions",
        json=build_request_payload(build_uniform_answers("SDS", "3")),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["questionnaire_code"] == "SDS"
    assert payload["risk_level"] == "watch"
    assert payload["hard_trigger_hit"] is False

    with app.state.db_session_factory() as session:
        submission = session.get(QuestionnaireSubmission, payload["submission_id"])
        assert submission is not None
        focus_entry = session.scalar(select(FocusListEntry))
        assert focus_entry is not None
        assert focus_entry.student_id == submission.student_id
        assert focus_entry.source_type is CaseSourceType.ASSESSMENT
        assert focus_entry.source_id == submission.id
        assert focus_entry.reason_code == "SDS_POSITIVE"
        assert focus_entry.status is FocusListStatus.ACTIVE
        assert "SDS" in focus_entry.reason_text
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 0
        student = session.get(StudentUser, submission.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.WATCH


def test_submit_screen_watch_result_does_not_create_focus_noise(tmp_path) -> None:
    """SCREEN watch results should stay local and avoid creating backend focus noise alone."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-screen-watch.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/questionnaires/screen/submissions",
        json=build_request_payload(build_uniform_answers("SCREEN", "3")),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["questionnaire_code"] == "SCREEN"
    assert payload["risk_level"] == "watch"

    with app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FocusListEntry)) == 0
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 0
        student = session.scalar(select(StudentUser))
        assert student is not None
        assert student.risk_status is StudentRiskStatus.NORMAL


def test_submit_sleep_watch_creates_focus_entry_after_required_chain_completion(
    tmp_path,
) -> None:
    """Sleep watch should only reach the focus list after the fixed required chain is complete."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-sleep-watch.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    for questionnaire_code in ("SCREEN", "SDS", "SAS"):
        response = client.post(
            f"/api/v1/questionnaires/{questionnaire_code.lower()}/submissions",
            json=build_request_payload(build_low_risk_answers(questionnaire_code)),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    sleep_seed = load_seed("SLEEP")
    sleep_answers = {
        question_seed.question_id: ("1" if index < 8 else "0")
        for index, question_seed in enumerate(sleep_seed.questions)
    }
    response = client.post(
        "/api/v1/questionnaires/sleep/submissions",
        json=build_request_payload(sleep_answers),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["questionnaire_code"] == "SLEEP"
    assert payload["risk_level"] == "watch"

    with app.state.db_session_factory() as session:
        submission = session.get(QuestionnaireSubmission, payload["submission_id"])
        assert submission is not None
        focus_entry = session.scalar(select(FocusListEntry))
        assert focus_entry is not None
        assert focus_entry.source_type is CaseSourceType.ASSESSMENT
        assert focus_entry.source_id == submission.id
        assert focus_entry.reason_code == "SLEEP_CONCERN"
        assert "睡眠" in focus_entry.reason_text
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 0
        student = session.get(StudentUser, submission.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.WATCH


def test_submit_low_risk_assessment_with_high_history_writes_review_focus_entry(
    tmp_path,
) -> None:
    """Historically high-risk students should still enter review focus when current assessment is neutral."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-history-review.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(
        app,
        risk_status=StudentRiskStatus.HIGH,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/questionnaires/sds/submissions",
        json=build_request_payload(build_low_risk_answers("SDS")),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["questionnaire_code"] == "SDS"
    assert payload["risk_level"] == "low"

    with app.state.db_session_factory() as session:
        submission = session.get(QuestionnaireSubmission, payload["submission_id"])
        assert submission is not None
        focus_entry = session.scalar(select(FocusListEntry))
        assert focus_entry is not None
        assert focus_entry.source_type is CaseSourceType.ASSESSMENT
        assert focus_entry.source_id == submission.id
        assert focus_entry.reason_code == "HISTORY_HIGH_REVIEW"
        assert "历史高风险记录" in focus_entry.reason_text
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 0
        student = session.get(StudentUser, submission.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.HIGH


def test_submit_upi_hard_trigger_returns_high_risk(tmp_path) -> None:
    """UPI hard triggers should upgrade risk and create a highest-priority alert case."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-upi-trigger.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/questionnaires/upi/submissions",
        json=build_request_payload(
            {
                "UPI_01": "yes",
                "UPI_02": "no",
                "UPI_03": "no",
                "UPI_04": "no",
            }
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["questionnaire_code"] == "UPI"
    assert payload["risk_level"] == "high"
    assert payload["hard_trigger_hit"] is True

    with app.state.db_session_factory() as session:
        submission = load_submission_with_answers(session, payload["submission_id"])
        assert submission.risk_level is QuestionnaireRiskLevel.HIGH
        assert submission.hard_trigger_hit is True
        assert submission.scoring_snapshot_json["hard_trigger_hit"] is True
        alert_case = session.scalar(select(AlertCase))
        assert alert_case is not None
        assert alert_case.student_id == submission.student_id
        assert alert_case.source_type is CaseSourceType.ASSESSMENT
        assert alert_case.source_submission_id == submission.id
        assert alert_case.queue_status is AlertQueueStatus.PENDING_REVIEW
        assert alert_case.review_priority is ReviewPriority.HIGHEST
        assert "UPI" in (alert_case.ai_reason_text or "")
        assert "HT-04" in (alert_case.ai_reason_text or "")
        student = session.get(StudentUser, submission.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.HIGH


def test_submit_sleep_high_risk_creates_urgent_alert_case(tmp_path) -> None:
    """Sleep-only high risk should create an urgent assessment alert without hard triggers."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-sleep-high.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/questionnaires/sleep/submissions",
        json=build_request_payload(build_uniform_answers("SLEEP", "3")),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["questionnaire_code"] == "SLEEP"
    assert payload["risk_level"] == "high"
    assert payload["hard_trigger_hit"] is False

    with app.state.db_session_factory() as session:
        submission = session.get(QuestionnaireSubmission, payload["submission_id"])
        assert submission is not None
        alert_case = session.scalar(select(AlertCase))
        assert alert_case is not None
        assert alert_case.student_id == submission.student_id
        assert alert_case.source_type is CaseSourceType.ASSESSMENT
        assert alert_case.source_submission_id == submission.id
        assert alert_case.queue_status is AlertQueueStatus.PENDING_REVIEW
        assert alert_case.review_priority is ReviewPriority.URGENT
        assert "SLEEP" in (alert_case.ai_reason_text or "")
        student = session.get(StudentUser, submission.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.HIGH


def test_submit_questionnaire_rejects_incomplete_answers_without_persistence(
    tmp_path,
) -> None:
    """Incomplete questionnaire submissions should return a business validation error."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-incomplete.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)
    answers = build_low_risk_answers("SCREEN")
    del answers["SCREEN_15"]

    response = client.post(
        "/api/v1/questionnaires/screen/submissions",
        json=build_request_payload(answers),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "QUESTIONNAIRE_SUBMISSION_INCOMPLETE"
    assert payload["message"] == "questionnaire submission is incomplete"
    assert payload["errors"] == [
        {
            "field": "answers.SCREEN_15",
            "reason": "missing answer",
        }
    ]

    with app.state.db_session_factory() as session:
        assert count_rows(session, QuestionnaireSubmission) == 0
        assert count_rows(session, QuestionnaireAnswer) == 0


def test_submit_questionnaire_rejects_invalid_answers_without_persistence(
    tmp_path,
) -> None:
    """Unsupported answer values should fail before any submission rows are committed."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-invalid.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)
    answers = build_low_risk_answers("SLEEP")
    answers["SLEEP_01"] = "9"

    response = client.post(
        "/api/v1/questionnaires/sleep/submissions",
        json=build_request_payload(answers),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "QUESTIONNAIRE_ANSWER_INVALID"
    assert "unsupported answer '9'" in payload["message"]

    with app.state.db_session_factory() as session:
        assert count_rows(session, QuestionnaireSubmission) == 0
        assert count_rows(session, QuestionnaireAnswer) == 0


def test_submit_questionnaire_returns_service_unavailable_when_db_is_not_seeded(
    tmp_path,
) -> None:
    """Known questionnaires should fail with 503 when runtime question bank data is missing."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-unseeded.db",
        import_question_bank=False,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/questionnaires/screen/submissions",
        json=build_request_payload(build_low_risk_answers("SCREEN")),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "QUESTIONNAIRE_CATALOG_UNAVAILABLE"
    assert "not initialized in database" in payload["message"]


def test_submit_questionnaire_requires_student_authentication(tmp_path) -> None:
    """Questionnaire submissions should reject unauthenticated requests."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-auth.db",
        import_question_bank=True,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/questionnaires/screen/submissions",
        json=build_request_payload(build_low_risk_answers("SCREEN")),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "student access token is required"


def test_submit_questionnaire_returns_not_found_for_unknown_code(tmp_path) -> None:
    """Unknown questionnaire codes should return a business 404 error."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-missing.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)

    response = client.post(
        "/api/v1/questionnaires/unknown/submissions",
        json={"answers": [{"question_code": "SCREEN_01", "selected_option": "1"}]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "QUESTIONNAIRE_NOT_FOUND"


def test_submit_questionnaire_persists_answer_rows_for_all_questions(tmp_path) -> None:
    """Persisted answer rows should be linked back to committed question bank IDs."""
    app = create_questionnaire_submission_test_app(
        tmp_path / "questionnaire-submit-answer-rows.db",
        import_question_bank=True,
    )
    _, token = create_student_with_token(app)
    client = TestClient(app)
    answers = build_low_risk_answers("SDS")

    response = client.post(
        "/api/v1/questionnaires/sds/submissions",
        json=build_request_payload(answers),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    submission_id = response.json()["data"]["submission_id"]

    with app.state.db_session_factory() as session:
        submission = load_submission_with_answers(session, submission_id)
        question_ids = {
            session.scalar(
                select(QuestionBank.id).where(
                    QuestionBank.question_code == question_code
                )
            )
            for question_code in answers
        }
        assert {answer.question_id for answer in submission.answers} == question_ids
        assert len(submission.answers) == len(answers)
