"""End-to-end API integration flows that exercise the core MVP chains in one test DB."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from src.constants.account_enums import AdminRoleCode
from src.core.settings import Settings
from src.main import create_app
from src.models import AdminUser, AlertCase, Base
from src.services.deepseek_service import (
    DEEPSEEK_MODEL_NAME,
    DeepSeekJsonCompletionResult,
)
from src.services.question_bank_seed_service import QuestionBankSeedService
from src.services.wechat_session_service import WeChatSession
from src.utils.validate_question_bank_seeds import load_seed_file

PASSWORD_HASHER = PasswordHash.recommended()
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
    """Create runtime settings for isolated integration-flow API tests."""
    return Settings(
        APP_NAME="心语 API 集成测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


class FakeDeepSeekService:
    """Deterministic DeepSeek stub used by integration-flow tests."""

    def __init__(self, *, result: DeepSeekJsonCompletionResult) -> None:
        self.result = result

    def create_json_completion_with_fallback(self, **_kwargs) -> DeepSeekJsonCompletionResult:
        return self.result


def build_mock_treehole_ai_result(
    *,
    risk_level: str,
    risk_score: str,
    recommended_action: str,
    emotion_tags: list[str],
    trigger_phrases: list[str],
    reason_text: str,
) -> DeepSeekJsonCompletionResult:
    """Build one normalized fake AI result for treehole integration tests."""
    content_json = {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "emotion_tags": emotion_tags,
        "trigger_phrases": trigger_phrases,
        "reason_text": reason_text,
        "recommended_action": recommended_action,
    }
    return DeepSeekJsonCompletionResult(
        request_payload={
            "model": DEEPSEEK_MODEL_NAME,
            "messages": [
                {"role": "system", "content": "Analyze treehole safety risk."},
                {"role": "user", "content": "integration test content"},
            ],
            "response_format": {"type": "json_object"},
        },
        response_payload={
            "source": "deepseek_api",
            "content": content_json,
        },
        completion_id="chatcmpl-integration-001",
        model_name=DEEPSEEK_MODEL_NAME,
        finish_reason="stop",
        content_text=json.dumps(content_json, ensure_ascii=False),
        content_json=content_json,
        fallback_used=False,
        fallback_reason=None,
    )


def create_integration_test_app(
    database_file: Path,
    *,
    deepseek_result: DeepSeekJsonCompletionResult,
):
    """Create one application with seeded question bank and deterministic AI service."""
    app = create_app(build_settings(database_file))
    app.state.deepseek_service = FakeDeepSeekService(result=deepseek_result)
    Base.metadata.create_all(app.state.db_engine)

    seed_paths = sorted(QUESTION_BANK_DIR.glob("*_questions.json"))
    with app.state.db_session_factory() as session:
        QuestionBankSeedService(session).import_seed_files(seed_paths)
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


def build_request_payload(answers: dict[str, str]) -> dict[str, object]:
    """Build a questionnaire-submission request body from one answer mapping."""
    return {
        "answers": [
            {
                "question_code": question_code,
                "selected_option": selected_option,
            }
            for question_code, selected_option in answers.items()
        ]
    }


def login_student_via_wechat(
    app,
    client: TestClient,
    *,
    openid: str,
    phone_number: str,
    college_name: str,
    class_name: str,
) -> dict[str, object]:
    """Log in one student through the public WeChat-login API."""
    app.state.wechat_session_service.exchange_login_code = lambda _code: WeChatSession(
        openid=openid,
        session_key=f"session-{openid}",
    )
    response = client.post(
        "/api/v1/auth/student/wechat-login",
        json={
            "login_code": f"login-{openid}",
            "phone_ticket": json.dumps(
                {
                    "phone_number": phone_number,
                    "college_name": college_name,
                    "class_name": class_name,
                }
            ),
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def submit_crisis_consent(
    client: TestClient,
    *,
    access_token: str,
    granted: bool,
) -> dict[str, object]:
    """Submit one crisis-intervention consent decision through the public API."""
    response = client.post(
        "/api/v1/consents",
        json={
            "consent_type": "crisis_intervention_authorization",
            "consent_version": "v1.0",
            "granted": granted,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def submit_questionnaire(
    client: TestClient,
    *,
    access_token: str,
    questionnaire_code: str,
) -> dict[str, object]:
    """Submit one low-risk questionnaire through the public API."""
    response = client.post(
        f"/api/v1/questionnaires/{questionnaire_code.lower()}/submissions",
        json=build_request_payload(build_low_risk_answers(questionnaire_code)),
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def login_admin(client: TestClient) -> str:
    """Authenticate the seeded administrator and return the bearer token."""
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "platform.admin", "password": "Admin#2026"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_student_login_questionnaire_unlock_and_low_risk_treehole_publish_flow(
    tmp_path,
) -> None:
    """One student should be able to log in, unlock the report, and publish a low-risk post."""
    app = create_integration_test_app(
        tmp_path / "integration-student-low-risk.db",
        deepseek_result=build_mock_treehole_ai_result(
            risk_level="low",
            risk_score="0.1200",
            recommended_action="publish",
            emotion_tags=["fatigue"],
            trigger_phrases=[],
            reason_text="当前文本未见明确高风险信号。",
        ),
    )
    client = TestClient(app)

    session_data = login_student_via_wechat(
        app,
        client,
        openid="wx-integration-low-risk",
        phone_number="13812345001",
        college_name="计算机学院",
        class_name="2026级1班",
    )
    assert session_data["student"]["consent_status"] == "missing"

    consent_data = submit_crisis_consent(
        client,
        access_token=str(session_data["access_token"]),
        granted=True,
    )
    student_token = str(consent_data["access_token"])
    assert consent_data["student"]["consent_status"] == "granted"

    for questionnaire_code in ("SCREEN", "SDS", "SAS", "SLEEP"):
        submission = submit_questionnaire(
            client,
            access_token=student_token,
            questionnaire_code=questionnaire_code,
        )
        assert submission["questionnaire_code"] == questionnaire_code
        assert submission["hard_trigger_hit"] is False

    summary_response = client.get(
        "/api/v1/reports/summary",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]["summary"]
    assert summary["state"] == "unlocked"
    assert summary["progress"]["required_questions_completed"] == 70
    assert summary["progress"]["full_profile_unlocked"] is True

    full_report_response = client.get(
        "/api/v1/reports/full",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert full_report_response.status_code == 200
    report = full_report_response.json()["data"]["report"]
    assert report["report_type"] == "full_profile"
    assert report["content"]["unlock_status"]["full_profile_unlocked"] is True
    assert report["risk_level"] == "low"

    create_post_response = client.post(
        "/api/v1/treehole/posts",
        json={"content": "今天终于把测评做完了，心里轻了一点。"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert create_post_response.status_code == 200
    post_payload = create_post_response.json()
    assert post_payload["message"] == "success"
    assert post_payload["data"]["publish_status"] == "published"
    assert post_payload["data"]["allow_publication"] is True
    post_id = int(post_payload["data"]["post_id"])

    feed_response = client.get(
        "/api/v1/treehole/feed",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert feed_response.status_code == 200
    posts = feed_response.json()["data"]["posts"]
    assert len(posts) == 1
    assert posts[0]["post_id"] == post_id
    assert posts[0]["content"] == post_payload["data"]["content_masked"]


def test_high_risk_treehole_intercept_and_admin_confirm_flow(tmp_path) -> None:
    """A blocked high-risk treehole post should create one alert that an admin can confirm."""
    app = create_integration_test_app(
        tmp_path / "integration-high-risk-admin.db",
        deepseek_result=build_mock_treehole_ai_result(
            risk_level="high",
            risk_score="0.9500",
            recommended_action="manual_review_high",
            emotion_tags=["despair"],
            trigger_phrases=["不想活了"],
            reason_text="检测到明确自伤或自杀意图，需要优先人工复核。",
        ),
    )
    create_admin_user(app)
    client = TestClient(app)

    session_data = login_student_via_wechat(
        app,
        client,
        openid="wx-integration-high-risk",
        phone_number="13812345002",
        college_name="心理学院",
        class_name="2026级2班",
    )
    consent_data = submit_crisis_consent(
        client,
        access_token=str(session_data["access_token"]),
        granted=True,
    )
    student_token = str(consent_data["access_token"])

    create_post_response = client.post(
        "/api/v1/treehole/posts",
        json={"content": "我真的不想活了，感觉没有任何意义。"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert create_post_response.status_code == 200
    post_payload = create_post_response.json()
    assert post_payload["message"] == "safety_intercepted"
    assert post_payload["data"]["risk_level"] == "high"
    assert post_payload["data"]["publish_status"] == "blocked_high_risk"
    assert post_payload["data"]["allow_publication"] is False

    student_feed_response = client.get(
        "/api/v1/treehole/feed",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert student_feed_response.status_code == 200
    assert student_feed_response.json()["data"]["posts"] == []

    admin_token = login_admin(client)
    pending_alerts_response = client.get(
        "/api/v1/admin/alerts",
        params={"queue_status": "pending_review"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pending_alerts_response.status_code == 200
    alert_items = pending_alerts_response.json()["data"]["items"]
    assert len(alert_items) == 1
    assert alert_items[0]["source_type"] == "treehole"
    alert_id = int(alert_items[0]["alert_id"])

    confirm_response = client.post(
        f"/api/v1/admin/alerts/{alert_id}/confirm",
        json={
            "review_note": "人工复核确认存在持续性危险表达。",
            "intervention_note": "已写入给辅导员的模拟联系说明。",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert confirm_response.status_code == 200
    confirm_payload = confirm_response.json()["data"]
    assert confirm_payload["queue_status"] == "confirmed_pending_intervention"
    assert "[SIMULATED]" in confirm_payload["simulated_notice_log"]

    confirmed_alerts_response = client.get(
        "/api/v1/admin/alerts",
        params={"queue_status": "confirmed_pending_intervention"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert confirmed_alerts_response.status_code == 200
    confirmed_items = confirmed_alerts_response.json()["data"]["items"]
    assert [item["alert_id"] for item in confirmed_items] == [alert_id]

    with app.state.db_session_factory() as session:
        alert_case = session.get(AlertCase, alert_id)
        assert alert_case is not None
        assert alert_case.queue_status.value == "confirmed_pending_intervention"
        assert alert_case.review_note == "人工复核确认存在持续性危险表达。"
        assert alert_case.simulated_notice_log is not None
        assert "[SIMULATED]" in alert_case.simulated_notice_log
