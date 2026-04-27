"""Aggregate AI, questionnaire, hard-trigger, and history signals into one risk level."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from src.constants.account_enums import StudentRiskStatus
from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.models.ai_analysis_record import AIAnalysisRecord
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.models.student_user import StudentUser
from src.models.treehole_post import TreeholePost

QUESTIONNAIRE_SIGNAL_ORDER = ("SCREEN", "SDS", "SAS", "SLEEP", "UPI")
REQUIRED_CHAIN_CODES = ("SCREEN", "SDS", "SAS", "SLEEP")


class RiskAggregationServiceError(ValueError):
    """Raised when risk aggregation cannot resolve the required student context."""


@dataclass(frozen=True, slots=True)
class AggregatedRiskResult:
    """Normalized aggregate risk output used by treehole and later workflow steps."""

    risk_level: QuestionnaireRiskLevel
    reason_codes: list[str]
    ai_risk_level: QuestionnaireRiskLevel | None
    hard_trigger_hit: bool
    history_high_risk: bool
    history_elevated: bool
    current_signals_neutral: bool
    has_questionnaire_data: bool
    required_chain_complete: bool
    latest_questionnaire_codes: list[str]


class RiskAggregationService:
    """Aggregate current AI signals, latest questionnaire results, and historical risk."""

    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def aggregate_treehole_risk(
        self,
        *,
        student: StudentUser,
        ai_risk_level: QuestionnaireRiskLevel | None,
    ) -> AggregatedRiskResult:
        """Load the student's latest context and aggregate the current treehole risk."""
        if self.session is None:
            raise RiskAggregationServiceError(
                "database session is required to aggregate treehole risk"
            )

        latest_submissions = self._load_latest_submissions(student.id)
        history_high_risk = self._has_historical_high_risk(student)
        return self.aggregate_signals(
            ai_risk_level=ai_risk_level,
            questionnaire_submissions=latest_submissions,
            history_high_risk=history_high_risk,
        )

    def aggregate_assessment_risk(
        self,
        *,
        student: StudentUser,
    ) -> AggregatedRiskResult:
        """Load the student's latest questionnaire context and aggregate assessment-only risk."""
        if self.session is None:
            raise RiskAggregationServiceError(
                "database session is required to aggregate assessment risk"
            )

        latest_submissions = self._load_latest_submissions(student.id)
        history_high_risk = self._has_historical_high_risk(student)
        return self.aggregate_signals(
            ai_risk_level=None,
            questionnaire_submissions=latest_submissions,
            history_high_risk=history_high_risk,
        )

    def aggregate_signals(
        self,
        *,
        ai_risk_level: QuestionnaireRiskLevel | None,
        questionnaire_submissions: Sequence[QuestionnaireSubmission],
        history_high_risk: bool,
    ) -> AggregatedRiskResult:
        """Aggregate current AI, latest questionnaire, hard-trigger, and history signals."""
        latest_submissions = self._select_latest_submissions(questionnaire_submissions)
        has_questionnaire_data = bool(latest_submissions)
        required_chain_complete = all(
            code in latest_submissions for code in REQUIRED_CHAIN_CODES
        )
        hard_trigger_hit = any(
            submission.hard_trigger_hit for submission in latest_submissions.values()
        )

        sds = latest_submissions.get("SDS")
        sas = latest_submissions.get("SAS")
        sleep = latest_submissions.get("SLEEP")

        high_reason_codes: list[str] = []
        if hard_trigger_hit:
            high_reason_codes.append("QUESTIONNAIRE_HARD_TRIGGER")
        if ai_risk_level is QuestionnaireRiskLevel.HIGH:
            high_reason_codes.append("TREEHOLE_AI_HIGH")
        if sds is not None and sds.risk_level is QuestionnaireRiskLevel.HIGH:
            high_reason_codes.append("SDS_HIGH")
        if sas is not None and sas.risk_level is QuestionnaireRiskLevel.HIGH:
            high_reason_codes.append("SAS_HIGH")

        watch_reason_codes: list[str] = []
        if ai_risk_level is QuestionnaireRiskLevel.WATCH:
            watch_reason_codes.append("TREEHOLE_AI_WATCH")
        if sds is not None and sds.risk_level is QuestionnaireRiskLevel.WATCH:
            watch_reason_codes.append("SDS_POSITIVE")
        if sas is not None and sas.risk_level is QuestionnaireRiskLevel.WATCH:
            watch_reason_codes.append("SAS_POSITIVE")

        # Sleep-only concern elevates the aggregate level only when the fixed required
        # chain is complete; this mirrors the PRD's complete-data rule and avoids
        # over-promoting incomplete single-signal cases before 9.4 publishes decisions.
        if (
            required_chain_complete
            and sleep is not None
            and sleep.risk_level in {QuestionnaireRiskLevel.WATCH, QuestionnaireRiskLevel.HIGH}
        ):
            watch_reason_codes.append("SLEEP_CONCERN")

        current_signals_neutral = not high_reason_codes and not watch_reason_codes
        history_elevated = history_high_risk and current_signals_neutral
        if history_elevated:
            watch_reason_codes.append("HISTORY_HIGH_REVIEW")

        if high_reason_codes:
            risk_level = QuestionnaireRiskLevel.HIGH
            reason_codes = high_reason_codes
        elif watch_reason_codes:
            risk_level = QuestionnaireRiskLevel.WATCH
            reason_codes = watch_reason_codes
        else:
            risk_level = QuestionnaireRiskLevel.LOW
            reason_codes = ["CURRENT_SIGNALS_STABLE"]

        return AggregatedRiskResult(
            risk_level=risk_level,
            reason_codes=reason_codes,
            ai_risk_level=ai_risk_level,
            hard_trigger_hit=hard_trigger_hit,
            history_high_risk=history_high_risk,
            history_elevated=history_elevated,
            current_signals_neutral=current_signals_neutral,
            has_questionnaire_data=has_questionnaire_data,
            required_chain_complete=required_chain_complete,
            latest_questionnaire_codes=self._ordered_questionnaire_codes(latest_submissions),
        )

    def _load_latest_submissions(
        self,
        student_id: int,
    ) -> list[QuestionnaireSubmission]:
        """Load all submissions for one student and keep only the latest per questionnaire."""
        if self.session is None:
            raise RiskAggregationServiceError(
                "database session is required to load questionnaire submissions"
            )

        statement = (
            select(QuestionnaireSubmission)
            .options(selectinload(QuestionnaireSubmission.template))
            .where(QuestionnaireSubmission.student_id == student_id)
        )
        submissions = list(self.session.scalars(statement).all())
        return list(self._select_latest_submissions(submissions).values())

    def _has_historical_high_risk(self, student: StudentUser) -> bool:
        """Return whether the student already has a stored high-risk history signal."""
        if student.risk_status is StudentRiskStatus.HIGH:
            return True
        if self.session is None:
            raise RiskAggregationServiceError(
                "database session is required to inspect historical risk"
            )

        high_submission_statement = (
            select(QuestionnaireSubmission.id)
            .where(
                QuestionnaireSubmission.student_id == student.id,
                or_(
                    QuestionnaireSubmission.hard_trigger_hit.is_(True),
                    QuestionnaireSubmission.risk_level == QuestionnaireRiskLevel.HIGH,
                ),
            )
            .limit(1)
        )
        if self.session.scalar(high_submission_statement) is not None:
            return True

        high_treehole_ai_statement = (
            select(AIAnalysisRecord.id)
            .join(TreeholePost, AIAnalysisRecord.target_id == TreeholePost.id)
            .where(
                TreeholePost.student_id == student.id,
                AIAnalysisRecord.parsed_risk_level == QuestionnaireRiskLevel.HIGH,
            )
            .limit(1)
        )
        return self.session.scalar(high_treehole_ai_statement) is not None

    def _select_latest_submissions(
        self,
        submissions: Sequence[QuestionnaireSubmission],
    ) -> dict[str, QuestionnaireSubmission]:
        """Keep only the latest submission per questionnaire code."""
        latest_by_code: dict[str, QuestionnaireSubmission] = {}
        for submission in submissions:
            questionnaire_code = self._resolve_questionnaire_code(submission)
            existing = latest_by_code.get(questionnaire_code)
            if existing is None or self._submission_sort_key(
                submission
            ) > self._submission_sort_key(existing):
                latest_by_code[questionnaire_code] = submission
        return latest_by_code

    def _resolve_questionnaire_code(
        self,
        submission: QuestionnaireSubmission,
    ) -> str:
        """Resolve questionnaire code from the scoring snapshot or ORM relationship."""
        snapshot = submission.scoring_snapshot_json or {}
        snapshot_code = snapshot.get("questionnaire_code")
        if isinstance(snapshot_code, str) and snapshot_code:
            return snapshot_code.upper()

        template = getattr(submission, "template", None)
        template_code = getattr(template, "code", None)
        if isinstance(template_code, str) and template_code:
            return template_code.upper()

        raise RiskAggregationServiceError(
            f"submission {submission.id} is missing questionnaire metadata"
        )

    def _ordered_questionnaire_codes(
        self,
        latest_submissions: dict[str, QuestionnaireSubmission],
    ) -> list[str]:
        """Return stable questionnaire-code ordering for downstream workflow logic."""
        known_codes = [code for code in QUESTIONNAIRE_SIGNAL_ORDER if code in latest_submissions]
        extra_codes = sorted(
            code for code in latest_submissions if code not in QUESTIONNAIRE_SIGNAL_ORDER
        )
        return [*known_codes, *extra_codes]

    def _submission_sort_key(
        self,
        submission: QuestionnaireSubmission,
    ) -> tuple[datetime, datetime, int]:
        """Return a stable ordering key for latest-submission comparisons."""
        created_at = getattr(submission, "created_at", None) or submission.submitted_at
        return (submission.submitted_at, created_at, submission.id or 0)
