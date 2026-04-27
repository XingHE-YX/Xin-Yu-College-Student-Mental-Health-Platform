"""Shared alert-case creation rules for automated risk workflows."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    CaseSourceType,
    ReviewPriority,
)
from src.models.alert_case import AlertCase
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.repositories.review_workflow_repository import ReviewWorkflowRepository
from src.services.questionnaire_scoring_service import QuestionnaireScoreResult

ACUTE_HIGH_RISK_ASSESSMENTS = frozenset({"SDS", "SAS"})


@dataclass(frozen=True, slots=True)
class CreatedAlertCaseResult:
    """Alert-case creation result with simple idempotency metadata."""

    alert_case: AlertCase
    created: bool


class AlertCaseService:
    """Centralize alert-case priority assignment and source-level idempotency."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ReviewWorkflowRepository(session)

    def create_treehole_high_risk_case(
        self,
        *,
        student_id: int,
        post_id: int,
        reason_text: str,
    ) -> CreatedAlertCaseResult:
        """Create one highest-priority alert case for a blocked high-risk treehole post."""
        return self._create_case(
            student_id=student_id,
            source_type=CaseSourceType.TREEHOLE,
            source_post_id=post_id,
            case_level=AlertCaseLevel.HIGH,
            review_priority=ReviewPriority.HIGHEST,
            reason_text=reason_text,
        )

    def create_assessment_high_risk_case(
        self,
        *,
        student_id: int,
        submission: QuestionnaireSubmission,
        score_result: QuestionnaireScoreResult,
    ) -> CreatedAlertCaseResult:
        """Create one alert case for a high-risk questionnaire submission."""
        if score_result.risk_level is not QuestionnaireRiskLevel.HIGH:
            raise ValueError(
                "only high-risk questionnaire submissions can create alert cases"
            )

        return self._create_case(
            student_id=student_id,
            source_type=CaseSourceType.ASSESSMENT,
            source_submission_id=submission.id,
            case_level=AlertCaseLevel.HIGH,
            review_priority=self._resolve_assessment_priority(score_result),
            reason_text=self._build_assessment_reason_text(score_result),
        )

    def _create_case(
        self,
        *,
        student_id: int,
        source_type: CaseSourceType,
        case_level: AlertCaseLevel,
        review_priority: ReviewPriority,
        reason_text: str,
        source_post_id: int | None = None,
        source_submission_id: int | None = None,
    ) -> CreatedAlertCaseResult:
        """Create one alert case or return the existing source-linked row."""
        existing_case = self._find_existing_case(
            source_type=source_type,
            source_post_id=source_post_id,
            source_submission_id=source_submission_id,
        )
        if existing_case is not None:
            return CreatedAlertCaseResult(alert_case=existing_case, created=False)

        alert_case = AlertCase(
            student_id=student_id,
            source_type=source_type,
            source_post_id=source_post_id,
            source_submission_id=source_submission_id,
            case_level=case_level,
            queue_status=AlertQueueStatus.PENDING_REVIEW,
            review_priority=review_priority,
            ai_reason_text=reason_text,
        )
        self.repository.add_alert_case(alert_case)
        return CreatedAlertCaseResult(alert_case=alert_case, created=True)

    def _find_existing_case(
        self,
        *,
        source_type: CaseSourceType,
        source_post_id: int | None,
        source_submission_id: int | None,
    ) -> AlertCase | None:
        """Return an existing alert case for one concrete source record, if any."""
        if source_post_id is None and source_submission_id is None:
            raise ValueError("alert-case source identifiers cannot both be omitted")

        statement = select(AlertCase).where(AlertCase.source_type == source_type)
        if source_post_id is not None:
            statement = statement.where(AlertCase.source_post_id == source_post_id)
        if source_submission_id is not None:
            statement = statement.where(
                AlertCase.source_submission_id == source_submission_id
            )
        return self.session.scalar(statement.limit(1))

    def _resolve_assessment_priority(
        self,
        score_result: QuestionnaireScoreResult,
    ) -> ReviewPriority:
        """Map high-risk questionnaire results onto queue priorities."""
        if score_result.hard_trigger_hit:
            return ReviewPriority.HIGHEST
        if score_result.questionnaire_code in ACUTE_HIGH_RISK_ASSESSMENTS:
            return ReviewPriority.HIGHEST
        return ReviewPriority.URGENT

    def _build_assessment_reason_text(
        self,
        score_result: QuestionnaireScoreResult,
    ) -> str:
        """Build a stable human-readable reason for assessment-triggered cases."""
        if score_result.standardized_score is None:
            score_text = f"原始分 {score_result.raw_score}"
        else:
            score_text = (
                f"原始分 {score_result.raw_score}，标准分 {score_result.standardized_score}"
            )

        reason_parts = [
            f"{score_result.questionnaire_code} 问卷结果达到高风险阈值（{score_text}）"
        ]
        if score_result.hard_trigger_matches:
            trigger_codes = "、".join(
                match.reason_code for match in score_result.hard_trigger_matches
            )
            trigger_questions = "、".join(
                match.question_code for match in score_result.hard_trigger_matches
            )
            reason_parts.append(
                f"命中硬触发 {trigger_codes}（题目 {trigger_questions}）"
            )
        return "；".join(reason_parts) + "。"
