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
    service = AssessmentReportService()
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
