"""Student-facing report query services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.constants.questionnaire_enums import AssessmentReportType, QuestionnaireRiskLevel
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.services.assessment_report_service import (
    AssessmentReportService,
    GeneratedAssessmentReport,
)


@dataclass(frozen=True, slots=True)
class ReportHistoryEntry:
    """One student-side report history item."""

    report_type: AssessmentReportType
    questionnaire_code: str
    questionnaire_name: str
    submitted_at: datetime
    result_title: str
    risk_level: QuestionnaireRiskLevel
    hard_trigger_hit: bool
    flow_step: str | None
    score_summary: list[dict[str, Any]]
    summary_text: str


class StudentReportService:
    """Load student questionnaire submissions and derive report payloads."""

    def __init__(
        self,
        session: Session,
        *,
        report_service: AssessmentReportService | None = None,
    ) -> None:
        self.session = session
        self.report_service = report_service or AssessmentReportService()

    def build_report_summary(self, *, student_id: int) -> dict[str, Any]:
        """Build the student report-home payload from current submissions."""
        submissions = self._load_student_submissions(student_id)
        return self.report_service.build_report_summary(submissions)

    def build_full_profile_report(
        self,
        *,
        student_id: int,
    ) -> GeneratedAssessmentReport:
        """Build the unlocked full-profile report for one student."""
        submissions = self._load_student_submissions(student_id)
        return self.report_service.build_full_profile_report(submissions)

    def build_report_history(self, *, student_id: int) -> list[ReportHistoryEntry]:
        """Build report-history items from all scored questionnaire submissions."""
        submissions = self._load_student_submissions(student_id)
        history_entries: list[ReportHistoryEntry] = []
        for submission in sorted(
            submissions,
            key=self._submission_sort_key,
            reverse=True,
        ):
            generated_report = self.report_service.build_scale_result_report(
                submission,
                submissions=submissions,
            )
            questionnaire_code = self._resolve_questionnaire_code(submission)
            questionnaire_entry = self.report_service.catalog_by_code[questionnaire_code]
            content = generated_report.content
            history_entries.append(
                ReportHistoryEntry(
                    report_type=generated_report.report_type,
                    questionnaire_code=questionnaire_code,
                    questionnaire_name=questionnaire_entry.name,
                    submitted_at=submission.submitted_at,
                    result_title=generated_report.result_title,
                    risk_level=submission.risk_level,
                    hard_trigger_hit=submission.hard_trigger_hit,
                    flow_step=content.get("page_flow_step"),
                    score_summary=content.get("score_summary", []),
                    summary_text=content.get("summary_text", ""),
                )
            )
        return history_entries

    def _load_student_submissions(
        self,
        student_id: int,
    ) -> list[QuestionnaireSubmission]:
        """Load all questionnaire submissions for the student."""
        statement = (
            select(QuestionnaireSubmission)
            .options(selectinload(QuestionnaireSubmission.template))
            .where(QuestionnaireSubmission.student_id == student_id)
        )
        return list(self.session.scalars(statement).all())

    def _resolve_questionnaire_code(self, submission: QuestionnaireSubmission) -> str:
        """Resolve questionnaire code from submission snapshot or ORM relation."""
        snapshot = submission.scoring_snapshot_json or {}
        snapshot_code = snapshot.get("questionnaire_code")
        if isinstance(snapshot_code, str) and snapshot_code:
            return snapshot_code.upper()

        template = getattr(submission, "template", None)
        template_code = getattr(template, "code", None)
        if isinstance(template_code, str) and template_code:
            return template_code.upper()

        raise ValueError(f"submission {submission.id} is missing questionnaire metadata")

    def _submission_sort_key(
        self,
        submission: QuestionnaireSubmission,
    ) -> tuple[datetime, datetime, int]:
        """Return a stable sort key for submission ordering."""
        created_at = getattr(submission, "created_at", None) or submission.submitted_at
        return (submission.submitted_at, created_at, submission.id or 0)
