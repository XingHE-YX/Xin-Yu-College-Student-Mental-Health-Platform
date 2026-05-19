"""Query services for questionnaire metadata and required-progress APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionType,
)
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.schemas.question_bank_seed import QuestionBankSeedFile, QuestionOptionSeed
from src.utils.validate_question_bank_seeds import (
    DEFAULT_SEED_DIRECTORY,
    discover_seed_files,
    load_seed_file,
)

QUESTIONNAIRE_DISPLAY_ORDER = ("SCREEN", "SDS", "SAS", "SLEEP", "UPI")
QUESTIONNAIRE_FLOW_STEP = {
    "SCREEN": "S05",
    "SDS": "S06",
    "SAS": "S07",
    "SLEEP": "S08",
    "UPI": "S09",
}


class QuestionnaireQueryError(ValueError):
    """Base error for questionnaire metadata lookup failures."""


class QuestionnaireCatalogUnavailableError(QuestionnaireQueryError):
    """Raised when committed questionnaire seed metadata cannot be loaded."""


class QuestionnaireNotFoundError(QuestionnaireQueryError):
    """Raised when one questionnaire code is not present in the catalog."""


@dataclass(frozen=True, slots=True)
class LatestSubmissionSummary:
    """Latest student submission metadata for one questionnaire."""

    submission_id: int
    submitted_at: datetime
    raw_score: int
    standardized_score: int | None
    risk_level: QuestionnaireRiskLevel
    hard_trigger_hit: bool

    @classmethod
    def from_submission(
        cls,
        submission: QuestionnaireSubmission,
    ) -> LatestSubmissionSummary:
        """Build a compact serializable summary from one submission row."""
        return cls(
            submission_id=submission.id,
            submitted_at=submission.submitted_at,
            raw_score=submission.raw_score,
            standardized_score=submission.standardized_score,
            risk_level=submission.risk_level,
            hard_trigger_hit=submission.hard_trigger_hit,
        )


@dataclass(frozen=True, slots=True)
class QuestionnaireListEntry:
    """Summary metadata for one questionnaire list item."""

    code: str
    name: str
    category: QuestionnaireCategory
    scoring_mode: QuestionnaireScoringMode
    question_count: int
    unlock_required: bool
    is_active: bool
    flow_step: str | None
    latest_submission: LatestSubmissionSummary | None


@dataclass(frozen=True, slots=True)
class QuestionnaireQuestionEntry:
    """Renderable question payload for one questionnaire detail response."""

    question_code: str
    question_order: int
    question_text: str
    question_type: QuestionType
    options: list[QuestionOptionSeed]


@dataclass(frozen=True, slots=True)
class QuestionnaireDetailEntry:
    """Full questionnaire metadata and renderable questions."""

    code: str
    name: str
    category: QuestionnaireCategory
    scoring_mode: QuestionnaireScoringMode
    question_count: int
    unlock_required: bool
    is_active: bool
    flow_step: str | None
    latest_submission: LatestSubmissionSummary | None
    questions: list[QuestionnaireQuestionEntry]


@dataclass(frozen=True, slots=True)
class RequiredProgressEntry:
    """One required questionnaire inside the fixed unlock-progress chain."""

    code: str
    name: str
    question_count: int
    flow_step: str | None
    completed: bool
    latest_submission: LatestSubmissionSummary | None


@dataclass(frozen=True, slots=True)
class QuestionnaireProgressSnapshot:
    """Fixed 70-question progress summary for the current student."""

    completed_required_questionnaires: int
    total_required_questionnaires: int
    completed_required_questions: int
    total_required_questions: int
    full_profile_unlocked: bool
    required_questionnaires: list[RequiredProgressEntry]


class QuestionnaireQueryService:
    """Load questionnaire catalog metadata and student-specific progress."""

    def __init__(
        self,
        session: Session,
        *,
        seed_directory: Path = DEFAULT_SEED_DIRECTORY,
    ) -> None:
        self.session = session
        self.catalog_by_code = self._load_catalog(seed_directory)

    def list_questionnaires(self, *, student_id: int) -> list[QuestionnaireListEntry]:
        """Return all active questionnaires in the canonical student flow order."""
        latest_submissions = self._load_latest_submissions(student_id)
        questionnaire_entries: list[QuestionnaireListEntry] = []
        for code in self._ordered_catalog_codes():
            seed_file = self.catalog_by_code[code]
            template = seed_file.template
            if not template.is_active:
                continue

            questionnaire_entries.append(
                QuestionnaireListEntry(
                    code=template.code,
                    name=template.name,
                    category=template.category,
                    scoring_mode=template.scoring_mode,
                    question_count=template.question_count,
                    unlock_required=template.unlock_required,
                    is_active=template.is_active,
                    flow_step=QUESTIONNAIRE_FLOW_STEP.get(template.code),
                    latest_submission=latest_submissions.get(template.code),
                )
            )
        return questionnaire_entries

    def get_questionnaire_detail(
        self,
        *,
        student_id: int,
        questionnaire_code: str,
    ) -> QuestionnaireDetailEntry:
        """Return one active questionnaire and its renderable question metadata."""
        normalized_code = questionnaire_code.upper()
        seed_file = self.catalog_by_code.get(normalized_code)
        if seed_file is None or not seed_file.template.is_active:
            raise QuestionnaireNotFoundError(
                f"questionnaire '{normalized_code}' does not exist"
            )

        latest_submissions = self._load_latest_submissions(student_id)
        return QuestionnaireDetailEntry(
            code=seed_file.template.code,
            name=seed_file.template.name,
            category=seed_file.template.category,
            scoring_mode=seed_file.template.scoring_mode,
            question_count=seed_file.template.question_count,
            unlock_required=seed_file.template.unlock_required,
            is_active=seed_file.template.is_active,
            flow_step=QUESTIONNAIRE_FLOW_STEP.get(seed_file.template.code),
            latest_submission=latest_submissions.get(seed_file.template.code),
            questions=[
                QuestionnaireQuestionEntry(
                    question_code=question.question_id,
                    question_order=question_order,
                    question_text=question.question_text,
                    question_type=question.question_type,
                    options=question.options,
                )
                for question_order, question in enumerate(seed_file.questions, start=1)
            ],
        )

    def get_required_progress(
        self,
        *,
        student_id: int,
    ) -> QuestionnaireProgressSnapshot:
        """Return progress across the fixed required 70-question unlock chain."""
        latest_submissions = self._load_latest_submissions(student_id)
        required_entries: list[RequiredProgressEntry] = []
        for code in self._ordered_catalog_codes():
            seed_file = self.catalog_by_code[code]
            template = seed_file.template
            if not template.is_active or not template.unlock_required:
                continue

            latest_submission = latest_submissions.get(template.code)
            required_entries.append(
                RequiredProgressEntry(
                    code=template.code,
                    name=template.name,
                    question_count=template.question_count,
                    flow_step=QUESTIONNAIRE_FLOW_STEP.get(template.code),
                    completed=latest_submission is not None,
                    latest_submission=latest_submission,
                )
            )

        completed_entries = [entry for entry in required_entries if entry.completed]
        completed_required_questions = sum(
            entry.question_count for entry in completed_entries
        )
        total_required_questions = sum(
            entry.question_count for entry in required_entries
        )
        return QuestionnaireProgressSnapshot(
            completed_required_questionnaires=len(completed_entries),
            total_required_questionnaires=len(required_entries),
            completed_required_questions=completed_required_questions,
            total_required_questions=total_required_questions,
            full_profile_unlocked=bool(required_entries)
            and len(completed_entries) == len(required_entries)
            and completed_required_questions == total_required_questions,
            required_questionnaires=required_entries,
        )

    def _load_catalog(self, seed_directory: Path) -> dict[str, QuestionBankSeedFile]:
        """Load and normalize questionnaire seed files from the committed catalog."""
        seed_paths = discover_seed_files(seed_directory)
        if not seed_paths:
            raise QuestionnaireCatalogUnavailableError(
                f"no questionnaire seed files found under {seed_directory}"
            )

        catalog_by_code: dict[str, QuestionBankSeedFile] = {}
        for seed_path in seed_paths:
            seed_file = load_seed_file(seed_path)
            normalized_code = seed_file.template.code.upper()
            if normalized_code in catalog_by_code:
                raise QuestionnaireCatalogUnavailableError(
                    f"duplicate questionnaire catalog entry '{normalized_code}'"
                )
            catalog_by_code[normalized_code] = seed_file
        return catalog_by_code

    def _ordered_catalog_codes(self) -> list[str]:
        """Return questionnaire codes in app-flow order with extras appended."""
        ordered_codes = [
            code for code in QUESTIONNAIRE_DISPLAY_ORDER if code in self.catalog_by_code
        ]
        ordered_codes.extend(
            sorted(code for code in self.catalog_by_code if code not in ordered_codes)
        )
        return ordered_codes

    def _load_latest_submissions(
        self,
        student_id: int,
    ) -> dict[str, LatestSubmissionSummary]:
        """Return the student's latest submission per questionnaire code."""
        statement = (
            select(QuestionnaireSubmission)
            .options(selectinload(QuestionnaireSubmission.template))
            .where(
                QuestionnaireSubmission.student_id == student_id,
                QuestionnaireSubmission.deleted_at.is_(None),
            )
        )
        submissions = self.session.scalars(statement).all()

        latest_by_code: dict[str, QuestionnaireSubmission] = {}
        for submission in submissions:
            questionnaire_code = self._resolve_submission_code(submission)
            existing_submission = latest_by_code.get(questionnaire_code)
            if existing_submission is None or self._submission_sort_key(
                submission
            ) > self._submission_sort_key(existing_submission):
                latest_by_code[questionnaire_code] = submission

        return {
            code: LatestSubmissionSummary.from_submission(submission)
            for code, submission in latest_by_code.items()
            if code in self.catalog_by_code
        }

    def _resolve_submission_code(self, submission: QuestionnaireSubmission) -> str:
        """Resolve questionnaire code from the submission snapshot or ORM relation."""
        snapshot = submission.scoring_snapshot_json or {}
        snapshot_code = snapshot.get("questionnaire_code")
        if isinstance(snapshot_code, str) and snapshot_code:
            return snapshot_code.upper()

        template = getattr(submission, "template", None)
        template_code = getattr(template, "code", None)
        if isinstance(template_code, str) and template_code:
            return template_code.upper()

        raise QuestionnaireCatalogUnavailableError(
            f"submission {submission.id} is missing questionnaire metadata"
        )

    def _submission_sort_key(
        self,
        submission: QuestionnaireSubmission,
    ) -> tuple[datetime, datetime, int]:
        """Return a stable ordering key for latest-submission comparisons."""
        created_at = getattr(submission, "created_at", None) or submission.submitted_at
        return (submission.submitted_at, created_at, submission.id or 0)
