"""Service layer for importing questionnaire seed files into the database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from src.repositories.question_bank_seed_repository import QuestionBankSeedRepository
from src.schemas.question_bank_seed import QuestionBankSeedFile
from src.utils.validate_question_bank_seeds import load_seed_file


@dataclass(slots=True)
class QuestionBankImportSummary:
    """Aggregate counters for one import run."""

    seed_files_processed: int = 0
    templates_created: int = 0
    templates_updated: int = 0
    questions_created: int = 0
    questions_updated: int = 0
    questions_deleted: int = 0


class QuestionBankSeedService:
    """Import questionnaire templates and question rows from validated seed files."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = QuestionBankSeedRepository(session)

    def import_seed_files(self, seed_paths: list[Path]) -> QuestionBankImportSummary:
        """Insert or refresh templates and question-bank rows from seed files."""
        summary = QuestionBankImportSummary(seed_files_processed=len(seed_paths))
        loaded_seed_files = [
            (seed_path, load_seed_file(seed_path)) for seed_path in seed_paths
        ]

        for seed_path, seed_file in loaded_seed_files:
            self._import_seed_file(seed_path, seed_file, summary)

        self.session.commit()
        return summary

    def _import_seed_file(
        self,
        seed_path: Path,
        seed_file: QuestionBankSeedFile,
        summary: QuestionBankImportSummary,
    ) -> None:
        """Insert or refresh one validated questionnaire seed file."""
        template = self.repository.get_template_by_code(seed_file.template.code)
        if template is None:
            template = self.repository.create_template(seed_file)
            summary.templates_created += 1
        else:
            self.repository.refresh_template(template, seed_file)
            summary.templates_updated += 1

        existing_questions = self.repository.list_questions_by_template_id(template.id)
        imported_question_codes: list[str] = []
        for question_order, question_seed in enumerate(seed_file.questions, start=1):
            imported_question_codes.append(question_seed.question_id)
            question = existing_questions.get(question_seed.question_id)

            if question is None:
                self.repository.create_question(
                    template_id=template.id,
                    question_order=question_order,
                    question_seed=question_seed,
                    seed_source=seed_path.name,
                )
                summary.questions_created += 1
                continue

            self.repository.refresh_question(
                question,
                question_order=question_order,
                question_seed=question_seed,
                seed_source=seed_path.name,
            )
            summary.questions_updated += 1

        summary.questions_deleted += self.repository.delete_questions_not_in(
            template_id=template.id,
            keep_question_codes=imported_question_codes,
        )
