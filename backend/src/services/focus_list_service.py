"""Shared focus-list creation rules for watch-level workflows."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.constants.workflow_enums import CaseSourceType
from src.models.focus_list_entry import FocusListEntry
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.repositories.review_workflow_repository import ReviewWorkflowRepository
from src.services.questionnaire_scoring_service import QuestionnaireScoreResult


@dataclass(frozen=True, slots=True)
class CreatedFocusListEntryResult:
    """Focus-list creation result with simple source-level idempotency metadata."""

    focus_entry: FocusListEntry
    created: bool


class FocusListService:
    """Centralize focus-list entry creation for watch-level cases."""

    def __init__(self, session: Session) -> None:
        self.repository = ReviewWorkflowRepository(session)

    def create_treehole_watch_entry(
        self,
        *,
        student_id: int,
        post_id: int,
        reason_code: str,
        reason_text: str,
    ) -> CreatedFocusListEntryResult:
        """Create one watch-list entry for a treehole post that stays public."""
        return self._create_entry(
            student_id=student_id,
            source_type=CaseSourceType.TREEHOLE,
            source_id=post_id,
            reason_code=reason_code,
            reason_text=reason_text,
        )

    def create_assessment_watch_entry(
        self,
        *,
        student_id: int,
        submission: QuestionnaireSubmission,
        score_result: QuestionnaireScoreResult,
        reason_code: str,
    ) -> CreatedFocusListEntryResult:
        """Create one watch-list entry for a questionnaire submission."""
        return self._create_entry(
            student_id=student_id,
            source_type=CaseSourceType.ASSESSMENT,
            source_id=submission.id,
            reason_code=reason_code,
            reason_text=self._build_assessment_reason_text(
                score_result=score_result,
                reason_code=reason_code,
            ),
        )

    def _create_entry(
        self,
        *,
        student_id: int,
        source_type: CaseSourceType,
        source_id: int,
        reason_code: str,
        reason_text: str,
    ) -> CreatedFocusListEntryResult:
        """Create one focus-list row or return the existing source-linked row."""
        existing_entry = self.repository.get_focus_list_entry_by_source(
            source_type=source_type,
            source_id=source_id,
            reason_code=reason_code,
        )
        if existing_entry is not None:
            return CreatedFocusListEntryResult(
                focus_entry=existing_entry,
                created=False,
            )

        focus_entry = FocusListEntry(
            student_id=student_id,
            source_type=source_type,
            source_id=source_id,
            reason_code=reason_code,
            reason_text=reason_text,
        )
        self.repository.add_focus_list_entry(focus_entry)
        return CreatedFocusListEntryResult(focus_entry=focus_entry, created=True)

    def _build_assessment_reason_text(
        self,
        *,
        score_result: QuestionnaireScoreResult,
        reason_code: str,
    ) -> str:
        """Build a stable human-readable reason for one watch-level assessment entry."""
        if score_result.standardized_score is None:
            score_text = f"原始分 {score_result.raw_score}"
        else:
            score_text = (
                f"原始分 {score_result.raw_score}，标准分 {score_result.standardized_score}"
            )

        if reason_code == "HISTORY_HIGH_REVIEW":
            return (
                f"{score_result.questionnaire_code} 最新结果当前稳定（{score_text}），"
                "但系统检测到历史高风险记录，建议纳入复查。"
            )
        if reason_code == "SLEEP_CONCERN":
            return f"{score_result.questionnaire_code} 问卷结果提示睡眠关注信号（{score_text}）。"

        return (
            f"{score_result.questionnaire_code} 问卷结果达到需关注阈值（{score_text}），"
            f"原因编码：{reason_code}。"
        )
