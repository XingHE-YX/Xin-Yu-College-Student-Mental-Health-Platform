"""Repository helpers for importing questionnaire seed files."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.question_bank import QuestionBank
from src.models.questionnaire_template import QuestionnaireTemplate
from src.schemas.question_bank_seed import QuestionBankSeedFile, QuestionSeed


class QuestionBankSeedRepository:
    """Persist questionnaire templates and question-bank rows from seed files."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_template_by_code(self, code: str) -> QuestionnaireTemplate | None:
        """Return a template by its unique code."""
        statement = select(QuestionnaireTemplate).where(
            QuestionnaireTemplate.code == code
        )
        return self.session.scalar(statement)

    def create_template(self, seed_file: QuestionBankSeedFile) -> QuestionnaireTemplate:
        """Create a questionnaire template from a validated seed file."""
        template = QuestionnaireTemplate(
            code=seed_file.template.code,
            name=seed_file.template.name,
            category=seed_file.template.category,
            question_count=seed_file.template.question_count,
            scoring_mode=seed_file.template.scoring_mode,
            unlock_required=seed_file.template.unlock_required,
            is_active=seed_file.template.is_active,
        )
        self.session.add(template)
        self.session.flush()
        return template

    def refresh_template(
        self,
        template: QuestionnaireTemplate,
        seed_file: QuestionBankSeedFile,
    ) -> None:
        """Update mutable template fields from a validated seed file."""
        template.name = seed_file.template.name
        template.category = seed_file.template.category
        template.question_count = seed_file.template.question_count
        template.scoring_mode = seed_file.template.scoring_mode
        template.unlock_required = seed_file.template.unlock_required
        template.is_active = seed_file.template.is_active

    def list_questions_by_template_id(
        self, template_id: int
    ) -> dict[str, QuestionBank]:
        """Return existing questions for one template keyed by question code."""
        statement = select(QuestionBank).where(QuestionBank.template_id == template_id)
        questions = self.session.scalars(statement).all()
        return {question.question_code: question for question in questions}

    def create_question(
        self,
        *,
        template_id: int,
        question_order: int,
        question_seed: QuestionSeed,
        seed_source: str,
    ) -> QuestionBank:
        """Create one question-bank row from a validated question seed."""
        question = QuestionBank(
            template_id=template_id,
            question_code=question_seed.question_id,
            question_order=question_order,
            question_text=question_seed.question_text,
            question_type=question_seed.question_type,
            options_json=[option.model_dump() for option in question_seed.options],
            score_mapping_json=question_seed.score_mapping,
            reverse_scored=question_seed.reverse_scored,
            hard_trigger_rule_json=(
                question_seed.hard_trigger_rule.model_dump()
                if question_seed.hard_trigger_rule is not None
                else None
            ),
            seed_source=seed_source,
        )
        self.session.add(question)
        return question

    def refresh_question(
        self,
        question: QuestionBank,
        *,
        question_order: int,
        question_seed: QuestionSeed,
        seed_source: str,
    ) -> None:
        """Refresh mutable question-bank fields from a validated question seed."""
        question.question_order = question_order
        question.question_text = question_seed.question_text
        question.question_type = question_seed.question_type
        question.options_json = [
            option.model_dump() for option in question_seed.options
        ]
        question.score_mapping_json = question_seed.score_mapping
        question.reverse_scored = question_seed.reverse_scored
        question.hard_trigger_rule_json = (
            question_seed.hard_trigger_rule.model_dump()
            if question_seed.hard_trigger_rule is not None
            else None
        )
        question.seed_source = seed_source

    def delete_questions_not_in(
        self,
        *,
        template_id: int,
        keep_question_codes: Iterable[str],
    ) -> int:
        """Delete stale question rows that no longer exist in the seed source."""
        keep_codes = tuple(keep_question_codes)
        if keep_codes:
            statement = delete(QuestionBank).where(
                QuestionBank.template_id == template_id,
                QuestionBank.question_code.not_in(keep_codes),
            )
        else:
            statement = delete(QuestionBank).where(
                QuestionBank.template_id == template_id
            )

        result = self.session.execute(statement)
        return result.rowcount or 0
