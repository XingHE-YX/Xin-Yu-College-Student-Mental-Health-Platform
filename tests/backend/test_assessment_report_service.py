"""Tests for assessment report generation and unlock logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.constants.questionnaire_enums import (
    AssessmentReportType,
    QuestionnaireRiskLevel,
    QuestionnaireSubmissionStatus,
)
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.services.assessment_report_service import (
    AssessmentReportService,
    FullProfileLockedError,
)
from src.services.deepseek_service import DEEPSEEK_MODEL_NAME, DeepSeekJsonCompletionResult


def build_submission(
    *,
    submission_id: int,
    questionnaire_code: str,
    submitted_at: datetime,
    raw_score: int,
    risk_level: QuestionnaireRiskLevel,
    standardized_score: int | None = None,
    student_id: int = 1,
    hard_trigger_hit: bool = False,
) -> QuestionnaireSubmission:
    """Build an in-memory scored submission for report-generation tests."""
    hard_trigger_matches = []
    if hard_trigger_hit:
        hard_trigger_matches.append(
            {
                "question_code": f"{questionnaire_code}_TRIGGER",
                "reason_code": f"HT-{submission_id}",
                "operator": "==",
                "expected_value": "yes",
                "matched_value": "yes",
            }
        )

    return QuestionnaireSubmission(
        id=submission_id,
        student_id=student_id,
        template_id=submission_id,
        started_at=submitted_at - timedelta(minutes=3),
        submitted_at=submitted_at,
        status=QuestionnaireSubmissionStatus.SCORED,
        raw_score=raw_score,
        standardized_score=standardized_score,
        risk_level=risk_level,
        hard_trigger_hit=hard_trigger_hit,
        scoring_snapshot_json={
            "questionnaire_code": questionnaire_code,
            "hard_trigger_matches": hard_trigger_matches,
        },
        created_at=submitted_at,
    )


class FakeDeepSeekService:
    """Deterministic DeepSeek stub used by report-generation tests."""

    def __init__(self, *, result: DeepSeekJsonCompletionResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def create_json_completion_with_fallback(self, **kwargs) -> DeepSeekJsonCompletionResult:
        self.calls.append(kwargs)
        return self.result


def build_mock_report_ai_result(
    *,
    fallback_used: bool = False,
    risk_level: str = "watch",
    analysis_summary: str = "AI 综合分析提示近期压力和睡眠状态需要继续留意。",
) -> DeepSeekJsonCompletionResult:
    """Build one normalized fake AI result for full-profile report tests."""
    content_json = {
        "analysis_summary": analysis_summary,
        "model_assessed_risk_level": risk_level,
        "dimensions": [
            {
                "name": "情绪状态",
                "level": risk_level,
                "evidence": "SDS 结果提示情绪状态需要结合近期生活事件观察。",
            }
        ],
        "risk_factors": ["近期压力累积。"],
        "protective_factors": ["已完成完整测评链路。"],
        "recommendations": [
            {
                "title": "稳定作息",
                "summary": "先保证睡眠、饮食和日常活动节律。",
            }
        ],
        "manual_review_hint": "建议继续观察，必要时进入重点关注。",
    }
    return DeepSeekJsonCompletionResult(
        request_payload={
            "model": DEEPSEEK_MODEL_NAME,
            "messages": [
                {"role": "system", "content": "Analyze report."},
                {"role": "user", "content": "fake report prompt"},
            ],
            "response_format": {"type": "json_object"},
        },
        response_payload={
            "source": "mock_report_response.json" if fallback_used else "deepseek_api",
            "content": content_json,
        },
        completion_id=None if fallback_used else "chatcmpl-report-test-001",
        model_name=DEEPSEEK_MODEL_NAME,
        finish_reason="mock_fallback" if fallback_used else "stop",
        content_text="{}",
        content_json=content_json,
        fallback_used=fallback_used,
        fallback_reason="DeepSeek chat completion timed out" if fallback_used else None,
    )


def test_scale_result_report_exposes_progress_and_frontend_hints() -> None:
    """Single-scale reports should contain progress and reusable UI metadata."""
    service = AssessmentReportService()
    now = datetime.now(UTC).replace(tzinfo=None)
    screen_submission = build_submission(
        submission_id=101,
        questionnaire_code="SCREEN",
        submitted_at=now,
        raw_score=46,
        risk_level=QuestionnaireRiskLevel.WATCH,
    )
    sds_submission = build_submission(
        submission_id=102,
        questionnaire_code="SDS",
        submitted_at=now + timedelta(minutes=5),
        raw_score=42,
        standardized_score=52,
        risk_level=QuestionnaireRiskLevel.LOW,
    )

    report = service.build_scale_result_report(
        screen_submission,
        submissions=[screen_submission, sds_submission],
    )

    assert report.report_type is AssessmentReportType.SCALE_RESULT
    assert report.result_title == "快速筛查结果"
    assert report.source_submission_ids == [101]
    assert report.content["page_flow_step"] == "S05"
    assert report.content["presentation"]["hero_component"] == "hero-card"
    assert report.content["result_badge"]["risk_level"] == "watch"
    assert report.content["score_summary"][0]["label"] == "总分"
    assert report.content["progress"]["required_questions_completed"] == 35
    assert report.content["progress"]["required_questions_total"] == 70
    assert report.content["next_actions"][0]["target_questionnaire_code"] == "SAS"
    assert "继续完成深度测评" in report.content["summary_text"]

    orm_report = report.to_model()
    assert orm_report.report_type is AssessmentReportType.SCALE_RESULT
    assert orm_report.source_submission_ids_json == [101]


def test_report_summary_stays_partial_until_all_required_questionnaires_finish() -> None:
    """The report-home state should remain partial before the 70 required answers exist."""
    service = AssessmentReportService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=201,
            questionnaire_code="SCREEN",
            submitted_at=now,
            raw_score=44,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=202,
            questionnaire_code="SDS",
            submitted_at=now + timedelta(minutes=4),
            raw_score=43,
            standardized_score=53,
            risk_level=QuestionnaireRiskLevel.WATCH,
        ),
    ]

    summary = service.build_report_summary(submissions)

    assert summary["state"] == "partial"
    assert summary["progress"]["required_questions_completed"] == 35
    assert summary["progress"]["required_questions_total"] == 70
    assert summary["overview_badge"]["risk_level"] == "watch"
    assert [item["code"] for item in summary["progress"]["missing_required_questionnaires"]] == [
        "SAS",
        "SLEEP",
    ]
    assert summary["next_actions"][0]["target_questionnaire_code"] == "SAS"
    assert len(summary["scale_results"]) == 2


def test_report_summary_is_locked_without_any_submissions() -> None:
    """The report-home state should stay locked until the first required questionnaire exists."""
    service = AssessmentReportService()

    summary = service.build_report_summary([])

    assert summary["state"] == "locked"
    assert summary["progress"]["required_questions_completed"] == 0
    assert summary["progress"]["required_questions_total"] == 70
    assert [item["code"] for item in summary["progress"]["missing_required_questionnaires"]] == [
        "SCREEN",
        "SDS",
        "SAS",
        "SLEEP",
    ]
    assert summary["next_actions"][0]["target_questionnaire_code"] == "SCREEN"
    assert summary["scale_results"] == []
    assert "overview_badge" not in summary


def test_report_summary_unlocks_with_exact_required_chain_without_upi() -> None:
    """The full profile should unlock once the four required questionnaires are complete."""
    service = AssessmentReportService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=211,
            questionnaire_code="SCREEN",
            submitted_at=now,
            raw_score=44,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=212,
            questionnaire_code="SDS",
            submitted_at=now + timedelta(minutes=1),
            raw_score=42,
            standardized_score=52,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=213,
            questionnaire_code="SAS",
            submitted_at=now + timedelta(minutes=2),
            raw_score=39,
            standardized_score=48,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=214,
            questionnaire_code="SLEEP",
            submitted_at=now + timedelta(minutes=3),
            raw_score=7,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
    ]

    summary = service.build_report_summary(submissions)

    assert summary["state"] == "unlocked"
    assert summary["progress"]["required_questions_completed"] == 70
    assert summary["progress"]["required_questions_total"] == 70
    assert summary["progress"]["full_profile_unlocked"] is True
    assert summary["progress"]["missing_required_questionnaires"] == []
    assert summary["overview_badge"]["risk_level"] == "low"
    assert [item["questionnaire"]["code"] for item in summary["scale_results"]] == [
        "SCREEN",
        "SDS",
        "SAS",
        "SLEEP",
    ]
    assert [item["flow_step"] for item in summary["next_actions"]] == ["S10A", "S15"]
    assert summary["next_actions"][0]["label"] == "查看完整报告"


def test_full_profile_requires_all_required_questionnaires() -> None:
    """Full-profile generation should fail until the required 70-question chain is complete."""
    service = AssessmentReportService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=301,
            questionnaire_code="SCREEN",
            submitted_at=now,
            raw_score=44,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=302,
            questionnaire_code="SDS",
            submitted_at=now + timedelta(minutes=2),
            raw_score=42,
            standardized_score=52,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=303,
            questionnaire_code="SAS",
            submitted_at=now + timedelta(minutes=4),
            raw_score=39,
            standardized_score=48,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
    ]

    with pytest.raises(FullProfileLockedError) as exc_info:
        service.build_full_profile_report(submissions)

    error = exc_info.value
    assert error.missing_questionnaire_codes == ["SLEEP"]
    assert error.completed_required_questions == 55
    assert error.total_required_questions == 70


def test_full_profile_uses_latest_submissions_and_sleep_high_maps_to_watch() -> None:
    """Latest submissions should win, and sleep-only high should not force overall high."""
    fake_deepseek_service = FakeDeepSeekService(result=build_mock_report_ai_result())
    service = AssessmentReportService(deepseek_service=fake_deepseek_service)
    now = datetime.now(UTC).replace(tzinfo=None)
    older_screen = build_submission(
        submission_id=401,
        questionnaire_code="SCREEN",
        submitted_at=now,
        raw_score=47,
        risk_level=QuestionnaireRiskLevel.WATCH,
    )
    latest_screen = build_submission(
        submission_id=402,
        questionnaire_code="SCREEN",
        submitted_at=now + timedelta(minutes=1),
        raw_score=41,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    sds = build_submission(
        submission_id=403,
        questionnaire_code="SDS",
        submitted_at=now + timedelta(minutes=2),
        raw_score=42,
        standardized_score=52,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    sas = build_submission(
        submission_id=404,
        questionnaire_code="SAS",
        submitted_at=now + timedelta(minutes=3),
        raw_score=39,
        standardized_score=48,
        risk_level=QuestionnaireRiskLevel.LOW,
    )
    sleep = build_submission(
        submission_id=405,
        questionnaire_code="SLEEP",
        submitted_at=now + timedelta(minutes=4),
        raw_score=15,
        risk_level=QuestionnaireRiskLevel.HIGH,
    )

    report = service.build_full_profile_report(
        [older_screen, latest_screen, sds, sas, sleep]
    )

    assert report.report_type is AssessmentReportType.FULL_PROFILE
    assert report.result_title == "完整综合画像报告"
    assert report.source_submission_ids == [402, 403, 404, 405]
    assert report.risk_level is QuestionnaireRiskLevel.WATCH
    assert report.content["unlock_status"]["full_profile_unlocked"] is True
    assert report.content["result_badge"]["risk_level"] == "watch"
    assert report.content["trend_placeholder"]["title"] == "趋势观察占位"
    assert fake_deepseek_service.calls
    system_prompt = fake_deepseek_service.calls[0]["system_prompt"]
    assert "extremely professional clinical-psychology expert" in system_prompt
    assert "warm" in system_prompt
    assert "comforting" in system_prompt
    ai_analysis = report.content["ai_integrated_analysis"]
    assert ai_analysis["provider"] == "deepseek"
    assert ai_analysis["model_name"] == DEEPSEEK_MODEL_NAME
    assert ai_analysis["model_assessed_risk_level"] == "watch"
    assert ai_analysis["fallback_used"] is False
    assert "AI 综合分析" in ai_analysis["analysis_summary"]
    assert ai_analysis["dimensions"][0]["name"] == "情绪状态"


def test_optional_upi_does_not_block_unlock_but_can_raise_full_profile_risk() -> None:
    """Optional UPI should not block unlocking, but a hard trigger can still upgrade risk."""
    service = AssessmentReportService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=501,
            questionnaire_code="SCREEN",
            submitted_at=now,
            raw_score=44,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=502,
            questionnaire_code="SDS",
            submitted_at=now + timedelta(minutes=1),
            raw_score=42,
            standardized_score=52,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=503,
            questionnaire_code="SAS",
            submitted_at=now + timedelta(minutes=2),
            raw_score=39,
            standardized_score=48,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=504,
            questionnaire_code="SLEEP",
            submitted_at=now + timedelta(minutes=3),
            raw_score=6,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=505,
            questionnaire_code="UPI",
            submitted_at=now + timedelta(minutes=4),
            raw_score=1,
            risk_level=QuestionnaireRiskLevel.HIGH,
            hard_trigger_hit=True,
        ),
    ]

    report = service.build_full_profile_report(submissions)

    assert report.source_submission_ids == [501, 502, 503, 504, 505]
    assert report.risk_level is QuestionnaireRiskLevel.HIGH
    assert report.content["unlock_status"]["full_profile_unlocked"] is True
    assert report.content["safety_banner"]["component"] == "safety-banner"
    assert report.content["questionnaire_summaries"][-1]["questionnaire"]["code"] == "UPI"


def test_full_profile_uses_rule_based_ai_block_when_deepseek_is_not_configured() -> None:
    """Full reports should still contain a report-analysis block without a DeepSeek service."""
    service = AssessmentReportService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=601,
            questionnaire_code="SCREEN",
            submitted_at=now,
            raw_score=44,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=602,
            questionnaire_code="SDS",
            submitted_at=now + timedelta(minutes=1),
            raw_score=42,
            standardized_score=52,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=603,
            questionnaire_code="SAS",
            submitted_at=now + timedelta(minutes=2),
            raw_score=39,
            standardized_score=48,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=604,
            questionnaire_code="SLEEP",
            submitted_at=now + timedelta(minutes=3),
            raw_score=6,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
    ]

    report = service.build_full_profile_report(submissions)

    ai_analysis = report.content["ai_integrated_analysis"]
    assert ai_analysis["provider"] == "deepseek"
    assert ai_analysis["model_name"] == "rule_based_fallback"
    assert ai_analysis["fallback_used"] is True
    assert ai_analysis["model_assessed_risk_level"] == "low"
    assert ai_analysis["dimensions"][0]["name"] == "快速筛查"
