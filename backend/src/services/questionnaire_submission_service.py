"""Service layer for questionnaire submissions and answer persistence."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.constants.account_enums import StudentRiskStatus
from src.constants.questionnaire_enums import (
    QuestionnaireRiskLevel,
    QuestionnaireSubmissionStatus,
)
from src.models.base import utc_now
from src.models.question_bank import QuestionBank
from src.models.questionnaire_answer import QuestionnaireAnswer
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.models.questionnaire_template import QuestionnaireTemplate
from src.repositories.student_user_repository import StudentUserRepository
from src.services.alert_case_service import AlertCaseService
from src.services.questionnaire_query_service import (
    QuestionnaireCatalogUnavailableError,
    QuestionnaireNotFoundError,
    QuestionnaireQueryService,
)
from src.services.questionnaire_scoring_service import (
    QuestionnaireScoreResult,
    QuestionnaireScoringService,
    ScoringQuestion,
)


@dataclass(frozen=True, slots=True)
class SubmittedQuestionAnswerInput:
    """One normalized answer received from the student client."""

    question_code: str
    selected_option: str


@dataclass(frozen=True, slots=True)
class SubmittedQuestionnaireResult:
    """Persisted questionnaire submission and its scoring output."""

    submission: QuestionnaireSubmission
    score_result: QuestionnaireScoreResult


class QuestionnaireSubmissionService:
    """Validate, score, and persist questionnaire submissions."""

    def __init__(
        self,
        session: Session,
        *,
        scoring_service: QuestionnaireScoringService | None = None,
    ) -> None:
        self.session = session
        self.scoring_service = scoring_service or QuestionnaireScoringService()
        self.catalog_by_code = QuestionnaireQueryService(session).catalog_by_code
        self.alert_case_service = AlertCaseService(session)
        self.student_repository = StudentUserRepository(session)

    def submit_questionnaire(
        self,
        *,
        student_id: int,
        questionnaire_code: str,
        answers: list[SubmittedQuestionAnswerInput],
    ) -> SubmittedQuestionnaireResult:
        """Score one questionnaire and persist submission plus answer details."""
        normalized_code = questionnaire_code.upper()
        seed_file = self.catalog_by_code.get(normalized_code)
        if seed_file is None or not seed_file.template.is_active:
            raise QuestionnaireNotFoundError(
                f"questionnaire '{normalized_code}' does not exist"
            )

        template, ordered_questions = self._load_runtime_questionnaire(normalized_code)
        self._validate_runtime_template(seed_file, template, ordered_questions)
        answers_by_code = self._normalize_answers(answers)
        score_result = self.scoring_service.score_questionnaire(
            questionnaire_code=template.code,
            scoring_mode=template.scoring_mode,
            questions=[
                ScoringQuestion.from_question_bank(question)
                for question in ordered_questions
            ],
            answers=answers_by_code,
        )

        submitted_at = utc_now()
        submission = QuestionnaireSubmission(
            student_id=student_id,
            template_id=template.id,
            started_at=submitted_at,
            submitted_at=submitted_at,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=score_result.raw_score,
            standardized_score=score_result.standardized_score,
            risk_level=score_result.risk_level,
            hard_trigger_hit=score_result.hard_trigger_hit,
            scoring_snapshot_json=score_result.to_snapshot(),
        )
        self.session.add(submission)
        self.session.flush()

        question_by_code = {
            question.question_code: question for question in ordered_questions
        }
        for scored_answer in score_result.scored_answers:
            question = question_by_code[scored_answer.question_code]
            self.session.add(
                QuestionnaireAnswer(
                    submission_id=submission.id,
                    question_id=question.id,
                    selected_option=scored_answer.selected_option,
                    raw_value=scored_answer.raw_value,
                    normalized_score=scored_answer.normalized_score,
                )
            )

        self._create_follow_up_records(
            student_id=student_id,
            submission=submission,
            score_result=score_result,
        )
        self.session.commit()
        self.session.refresh(submission)
        return SubmittedQuestionnaireResult(
            submission=submission,
            score_result=score_result,
        )

    def _create_follow_up_records(
        self,
        *,
        student_id: int,
        submission: QuestionnaireSubmission,
        score_result: QuestionnaireScoreResult,
    ) -> None:
        """Create assessment alert cases for high-risk results and persist student risk."""
        if score_result.risk_level is not QuestionnaireRiskLevel.HIGH:
            return

        student = self.student_repository.get_by_id(student_id)
        if student is None:
            raise ValueError(f"student '{student_id}' does not exist")

        self.alert_case_service.create_assessment_high_risk_case(
            student_id=student_id,
            submission=submission,
            score_result=score_result,
        )
        if student.risk_status is not StudentRiskStatus.HIGH:
            self.student_repository.update_risk_status(
                student,
                risk_status=StudentRiskStatus.HIGH,
            )

    def _load_runtime_questionnaire(
        self,
        questionnaire_code: str,
    ) -> tuple[QuestionnaireTemplate, list[QuestionBank]]:
        """Load one questionnaire template plus ordered questions from the database."""
        statement = (
            select(QuestionnaireTemplate)
            .options(selectinload(QuestionnaireTemplate.questions))
            .where(QuestionnaireTemplate.code == questionnaire_code)
        )
        template = self.session.scalar(statement)
        if template is None:
            raise QuestionnaireCatalogUnavailableError(
                f"questionnaire '{questionnaire_code}' is not initialized in database"
            )

        ordered_questions = sorted(
            template.questions,
            key=lambda question: (question.question_order, question.id),
        )
        if not ordered_questions:
            raise QuestionnaireCatalogUnavailableError(
                f"questionnaire '{questionnaire_code}' has no question bank rows"
            )
        return template, ordered_questions

    def _validate_runtime_template(
        self,
        seed_file,
        template: QuestionnaireTemplate,
        ordered_questions: list[QuestionBank],
    ) -> None:
        """Ensure runtime database metadata still matches the committed seed contract."""
        seed_template = seed_file.template
        if template.question_count != seed_template.question_count:
            raise QuestionnaireCatalogUnavailableError(
                f"questionnaire '{template.code}' question_count does not match seed metadata"
            )
        if template.scoring_mode is not seed_template.scoring_mode:
            raise QuestionnaireCatalogUnavailableError(
                f"questionnaire '{template.code}' scoring_mode does not match seed metadata"
            )
        if template.unlock_required != seed_template.unlock_required:
            raise QuestionnaireCatalogUnavailableError(
                f"questionnaire '{template.code}' unlock_required does not match seed metadata"
            )
        if template.is_active != seed_template.is_active:
            raise QuestionnaireCatalogUnavailableError(
                f"questionnaire '{template.code}' active status does not match seed metadata"
            )

        if len(ordered_questions) != len(seed_file.questions):
            raise QuestionnaireCatalogUnavailableError(
                f"questionnaire '{template.code}' question rows do not match seed metadata"
            )

        for expected_order, (question, seed_question) in enumerate(
            zip(ordered_questions, seed_file.questions, strict=True),
            start=1,
        ):
            if question.question_order != expected_order:
                raise QuestionnaireCatalogUnavailableError(
                    f"questionnaire '{template.code}' question order is out of sync"
                )
            if question.question_code != seed_question.question_id:
                raise QuestionnaireCatalogUnavailableError(
                    f"questionnaire '{template.code}' question codes do not match seed metadata"
                )
            if question.question_type is not seed_question.question_type:
                raise QuestionnaireCatalogUnavailableError(
                    f"questionnaire '{template.code}' question types do not match seed metadata"
                )
            if question.options_json != [
                option.model_dump() for option in seed_question.options
            ]:
                raise QuestionnaireCatalogUnavailableError(
                    f"questionnaire '{template.code}' options do not match seed metadata"
                )
            if question.score_mapping_json != seed_question.score_mapping:
                raise QuestionnaireCatalogUnavailableError(
                    f"questionnaire '{template.code}' score mappings do not match seed metadata"
                )
            if question.reverse_scored != seed_question.reverse_scored:
                raise QuestionnaireCatalogUnavailableError(
                    f"questionnaire '{template.code}' reverse scoring does not match seed metadata"
                )
            expected_hard_trigger = (
                seed_question.hard_trigger_rule.model_dump()
                if seed_question.hard_trigger_rule is not None
                else None
            )
            if question.hard_trigger_rule_json != expected_hard_trigger:
                raise QuestionnaireCatalogUnavailableError(
                    f"questionnaire '{template.code}' hard trigger rules do not match seed metadata"
                )

    def _normalize_answers(
        self,
        answers: list[SubmittedQuestionAnswerInput],
    ) -> dict[str, str]:
        """Convert submitted answers into a unique question-code mapping."""
        answers_by_code: dict[str, str] = {}
        duplicate_codes: list[str] = []
        for answer in answers:
            normalized_code = answer.question_code.upper()
            if normalized_code in answers_by_code:
                duplicate_codes.append(normalized_code)
                continue
            answers_by_code[normalized_code] = answer.selected_option

        if duplicate_codes:
            duplicate_text = ", ".join(sorted(set(duplicate_codes)))
            raise ValueError(f"duplicate answers for: {duplicate_text}")
        return answers_by_code
