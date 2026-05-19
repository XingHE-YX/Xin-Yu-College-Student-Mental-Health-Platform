"""Tests for aggregated risk rules across AI, questionnaires, hard triggers, and history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.constants.account_enums import StudentRiskStatus
from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionnaireSubmissionStatus,
)
from src.constants.treehole_enums import (
    AIAnalysisProvider,
    AIAnalysisTargetType,
    AIRecommendedAction,
    TreeholeAIStatus,
    TreeholePublishStatus,
)
from src.models import (
    AIAnalysisRecord,
    Base,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)
from src.services.risk_aggregation_service import RiskAggregationService


def build_submission(
    *,
    submission_id: int,
    questionnaire_code: str,
    submitted_at: datetime,
    risk_level: QuestionnaireRiskLevel,
    raw_score: int = 40,
    standardized_score: int | None = None,
    student_id: int = 1,
    hard_trigger_hit: bool = False,
) -> QuestionnaireSubmission:
    """Build one in-memory questionnaire submission for pure aggregation tests."""
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
        },
        created_at=submitted_at,
    )


def test_aggregate_signals_with_treehole_watch_only_returns_watch() -> None:
    """AI watch should elevate a treehole-only case to watch when no questionnaires exist."""
    service = RiskAggregationService()

    result = service.aggregate_signals(
        ai_risk_level=QuestionnaireRiskLevel.WATCH,
        questionnaire_submissions=[],
        history_high_risk=False,
    )

    assert result.risk_level is QuestionnaireRiskLevel.WATCH
    assert result.reason_codes == ["TREEHOLE_AI_WATCH"]
    assert result.has_questionnaire_data is False
    assert result.required_chain_complete is False
    assert result.current_signals_neutral is False


def test_aggregate_signals_with_treehole_high_only_returns_high() -> None:
    """AI high should immediately force a high-risk aggregate result."""
    service = RiskAggregationService()

    result = service.aggregate_signals(
        ai_risk_level=QuestionnaireRiskLevel.HIGH,
        questionnaire_submissions=[],
        history_high_risk=False,
    )

    assert result.risk_level is QuestionnaireRiskLevel.HIGH
    assert result.reason_codes == ["TREEHOLE_AI_HIGH"]
    assert result.hard_trigger_hit is False
    assert result.current_signals_neutral is False


def test_aggregate_signals_with_required_chain_complete_maps_sleep_high_to_watch() -> None:
    """Sleep concern should elevate risk only after the fixed required chain is complete."""
    service = RiskAggregationService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=101,
            questionnaire_code="SCREEN",
            submitted_at=now,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=102,
            questionnaire_code="SDS",
            submitted_at=now + timedelta(minutes=1),
            risk_level=QuestionnaireRiskLevel.LOW,
            standardized_score=52,
        ),
        build_submission(
            submission_id=103,
            questionnaire_code="SAS",
            submitted_at=now + timedelta(minutes=2),
            risk_level=QuestionnaireRiskLevel.LOW,
            standardized_score=48,
        ),
        build_submission(
            submission_id=104,
            questionnaire_code="SLEEP",
            submitted_at=now + timedelta(minutes=3),
            risk_level=QuestionnaireRiskLevel.HIGH,
            raw_score=18,
        ),
    ]

    result = service.aggregate_signals(
        ai_risk_level=QuestionnaireRiskLevel.LOW,
        questionnaire_submissions=submissions,
        history_high_risk=False,
    )

    assert result.risk_level is QuestionnaireRiskLevel.WATCH
    assert "SLEEP_CONCERN" in result.reason_codes
    assert result.required_chain_complete is True
    assert result.latest_questionnaire_codes == ["SCREEN", "SDS", "SAS", "SLEEP"]


def test_aggregate_signals_with_sas_watch_returns_watch() -> None:
    """A latest SAS watch result should elevate the aggregate level to watch."""
    service = RiskAggregationService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=151,
            questionnaire_code="SAS",
            submitted_at=now,
            risk_level=QuestionnaireRiskLevel.WATCH,
            raw_score=40,
            standardized_score=50,
        ),
    ]

    result = service.aggregate_signals(
        ai_risk_level=QuestionnaireRiskLevel.LOW,
        questionnaire_submissions=submissions,
        history_high_risk=False,
    )

    assert result.risk_level is QuestionnaireRiskLevel.WATCH
    assert result.reason_codes == ["SAS_POSITIVE"]
    assert result.latest_questionnaire_codes == ["SAS"]
    assert result.required_chain_complete is False


def test_aggregate_signals_with_incomplete_chain_does_not_raise_on_sleep_only_concern() -> None:
    """Incomplete-data rules should not promote a sleep-only signal by itself."""
    service = RiskAggregationService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=201,
            questionnaire_code="SCREEN",
            submitted_at=now,
            risk_level=QuestionnaireRiskLevel.LOW,
        ),
        build_submission(
            submission_id=202,
            questionnaire_code="SLEEP",
            submitted_at=now + timedelta(minutes=1),
            risk_level=QuestionnaireRiskLevel.HIGH,
            raw_score=18,
        ),
    ]

    result = service.aggregate_signals(
        ai_risk_level=QuestionnaireRiskLevel.LOW,
        questionnaire_submissions=submissions,
        history_high_risk=False,
    )

    assert result.risk_level is QuestionnaireRiskLevel.LOW
    assert result.reason_codes == ["CURRENT_SIGNALS_STABLE"]
    assert result.required_chain_complete is False
    assert result.current_signals_neutral is True


def test_aggregate_signals_with_hard_trigger_returns_high() -> None:
    """Any questionnaire hard trigger should override watch-level signals and force high."""
    service = RiskAggregationService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=301,
            questionnaire_code="UPI",
            submitted_at=now,
            risk_level=QuestionnaireRiskLevel.HIGH,
            raw_score=1,
            hard_trigger_hit=True,
        )
    ]

    result = service.aggregate_signals(
        ai_risk_level=QuestionnaireRiskLevel.WATCH,
        questionnaire_submissions=submissions,
        history_high_risk=False,
    )

    assert result.risk_level is QuestionnaireRiskLevel.HIGH
    assert "QUESTIONNAIRE_HARD_TRIGGER" in result.reason_codes
    assert result.hard_trigger_hit is True


@pytest.mark.parametrize(
    ("questionnaire_code", "reason_code", "standardized_score"),
    [
        ("SDS", "SDS_HIGH", 63),
        ("SAS", "SAS_HIGH", 60),
    ],
)
def test_aggregate_signals_with_scale_high_returns_high(
    questionnaire_code: str,
    reason_code: str,
    standardized_score: int,
) -> None:
    """Latest SDS/SAS high results should each force a high aggregate level."""
    service = RiskAggregationService()
    now = datetime.now(UTC).replace(tzinfo=None)
    submissions = [
        build_submission(
            submission_id=311,
            questionnaire_code=questionnaire_code,
            submitted_at=now,
            risk_level=QuestionnaireRiskLevel.HIGH,
            standardized_score=standardized_score,
        ),
    ]

    result = service.aggregate_signals(
        ai_risk_level=QuestionnaireRiskLevel.LOW,
        questionnaire_submissions=submissions,
        history_high_risk=False,
    )

    assert result.risk_level is QuestionnaireRiskLevel.HIGH
    assert result.reason_codes == [reason_code]
    assert result.hard_trigger_hit is False


def test_aggregate_signals_history_high_elevates_neutral_current_state_to_watch() -> None:
    """Historical high risk should promote an otherwise neutral current case to watch."""
    service = RiskAggregationService()

    result = service.aggregate_signals(
        ai_risk_level=QuestionnaireRiskLevel.LOW,
        questionnaire_submissions=[],
        history_high_risk=True,
    )

    assert result.risk_level is QuestionnaireRiskLevel.WATCH
    assert result.reason_codes == ["HISTORY_HIGH_REVIEW"]
    assert result.history_high_risk is True
    assert result.history_elevated is True
    assert result.current_signals_neutral is True


def test_aggregate_treehole_risk_uses_latest_submissions_and_historical_high_submission() -> None:
    """Older high questionnaire results should count as history while latest low results stay current."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC).replace(tzinfo=None)

    with Session(engine) as session:
        student = StudentUser(
            phone_e164="+8613812345601",
            wechat_openid="wx-risk-001",
            display_nickname="风险聚合同学",
            display_avatar_seed="seed-risk-001",
            college_name="心理学院",
            class_name="2026级1班",
            risk_status=StudentRiskStatus.NORMAL,
        )
        template = QuestionnaireTemplate(
            code="SDS",
            name="SDS 抑郁量表",
            category=QuestionnaireCategory.REQUIRED,
            question_count=20,
            scoring_mode=QuestionnaireScoringMode.ZUNG_STANDARD,
            unlock_required=True,
            is_active=True,
        )
        session.add_all([student, template])
        session.flush()

        session.add_all(
            [
                QuestionnaireSubmission(
                    student_id=student.id,
                    template_id=template.id,
                    started_at=now - timedelta(minutes=7),
                    submitted_at=now - timedelta(minutes=5),
                    status=QuestionnaireSubmissionStatus.SCORED,
                    raw_score=56,
                    standardized_score=70,
                    risk_level=QuestionnaireRiskLevel.HIGH,
                    hard_trigger_hit=False,
                    scoring_snapshot_json={"questionnaire_code": "SDS"},
                    created_at=now - timedelta(minutes=5),
                ),
                QuestionnaireSubmission(
                    student_id=student.id,
                    template_id=template.id,
                    started_at=now - timedelta(minutes=2),
                    submitted_at=now - timedelta(minutes=1),
                    status=QuestionnaireSubmissionStatus.SCORED,
                    raw_score=40,
                    standardized_score=50,
                    risk_level=QuestionnaireRiskLevel.LOW,
                    hard_trigger_hit=False,
                    scoring_snapshot_json={"questionnaire_code": "SDS"},
                    created_at=now - timedelta(minutes=1),
                ),
            ]
        )
        session.commit()
        session.refresh(student)

        result = RiskAggregationService(session).aggregate_treehole_risk(
            student=student,
            ai_risk_level=QuestionnaireRiskLevel.LOW,
        )

        assert result.risk_level is QuestionnaireRiskLevel.WATCH
        assert result.reason_codes == ["HISTORY_HIGH_REVIEW"]
        assert result.history_high_risk is True
        assert result.history_elevated is True
        assert result.latest_questionnaire_codes == ["SDS"]

    engine.dispose()


def test_aggregate_treehole_risk_detects_historical_high_ai_records() -> None:
    """Historical high treehole AI results should also trigger review on a neutral current case."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC).replace(tzinfo=None)

    with Session(engine) as session:
        student = StudentUser(
            phone_e164="+8613812345602",
            wechat_openid="wx-risk-002",
            display_nickname="历史树洞同学",
            display_avatar_seed="seed-risk-002",
            college_name="计算机学院",
            class_name="2026级2班",
            risk_status=StudentRiskStatus.NORMAL,
        )
        session.add(student)
        session.flush()

        post = TreeholePost(
            student_id=student.id,
            anonymous_name=student.display_nickname,
            anonymous_avatar_key=student.display_avatar_seed,
            content_raw="原始树洞高风险内容",
            content_masked="公开内容不会看到这段原文",
            ai_status=TreeholeAIStatus.ANALYZED,
            publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
            risk_level=QuestionnaireRiskLevel.LOW,
            allow_publication=False,
            hug_count=0,
            published_at=now - timedelta(days=1),
        )
        session.add(post)
        session.flush()

        session.add(
            AIAnalysisRecord(
                target_type=AIAnalysisTargetType.TREEHOLE_POST,
                target_id=post.id,
                provider=AIAnalysisProvider.DEEPSEEK,
                model_name="deepseek-v4-flash",
                request_payload_json={"content": post.content_raw},
                response_raw_json={"risk_level": "high"},
                parsed_risk_level=QuestionnaireRiskLevel.HIGH,
                parsed_risk_score=Decimal("0.9500"),
                emotion_tags_json=["despair"],
                trigger_phrases_json=["不想活了"],
                reason_text="检测到明确自伤意图。",
                recommended_action=AIRecommendedAction.MANUAL_REVIEW_HIGH,
                fallback_used=False,
            )
        )
        session.commit()
        session.refresh(student)

        result = RiskAggregationService(session).aggregate_treehole_risk(
            student=student,
            ai_risk_level=QuestionnaireRiskLevel.LOW,
        )

        assert result.risk_level is QuestionnaireRiskLevel.WATCH
        assert result.reason_codes == ["HISTORY_HIGH_REVIEW"]
        assert result.history_high_risk is True
        assert result.has_questionnaire_data is False

    engine.dispose()
