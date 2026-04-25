"""Tests for importing question-bank seed files into the database."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from src.models import Base, QuestionBank, QuestionnaireTemplate
from src.services.question_bank_seed_service import QuestionBankSeedService
from src.utils.import_question_bank_seeds import main as import_question_bank_main

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTION_BANK_DIR = REPO_ROOT / "appendices" / "question_bank"


def write_seed_file(path: Path, payload: dict) -> None:
    """Persist one JSON seed payload for import tests."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_seed_payload(question_count: int, *, template_name: str) -> dict:
    """Build a small valid SCREEN seed payload for import and refresh tests."""
    questions = []
    for index in range(1, question_count + 1):
        question_id = f"SCREEN_{index:02d}"
        questions.append(
            {
                "question_id": question_id,
                "question_text": f"{template_name} 第 {index} 题",
                "question_type": "single_choice",
                "options": [
                    {"value": "1", "label": "从不"},
                    {"value": "5", "label": "总是"},
                ],
                "score_mapping": {"1": 1, "5": 5},
                "reverse_scored": False,
                "hard_trigger_rule": None,
            }
        )

    return {
        "template": {
            "code": "SCREEN",
            "name": template_name,
            "category": "required",
            "question_count": question_count,
            "scoring_mode": "sum_1_5",
            "unlock_required": True,
            "is_active": True,
        },
        "questions": questions,
    }


def create_question_bank_schema() -> Session:
    """Create an isolated SQLite session with only questionnaire seed tables."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[QuestionnaireTemplate.__table__, QuestionBank.__table__],
    )
    return Session(engine)


def test_import_service_initializes_empty_database_from_real_seed_files() -> None:
    """Importing the committed seed files should populate all templates and questions."""
    seed_paths = sorted(QUESTION_BANK_DIR.glob("*.json"))
    with create_question_bank_schema() as session:
        summary = QuestionBankSeedService(session).import_seed_files(seed_paths)

        template_count = session.scalar(
            select(func.count()).select_from(QuestionnaireTemplate)
        )
        question_count = session.scalar(select(func.count()).select_from(QuestionBank))
        seed_sources = set(session.scalars(select(QuestionBank.seed_source)).all())

    assert summary.seed_files_processed == 5
    assert summary.templates_created == 5
    assert summary.templates_updated == 0
    assert summary.questions_created == 74
    assert summary.questions_updated == 0
    assert summary.questions_deleted == 0
    assert template_count == 5
    assert question_count == 74
    assert seed_sources == {
        "sas_questions.json",
        "screen_questions.json",
        "sds_questions.json",
        "sleep_questions.json",
        "upi_questions.json",
    }


def test_import_service_refreshes_existing_template_and_deletes_stale_questions(
    tmp_path: Path,
) -> None:
    """Re-importing a seed file should update existing rows and remove stale questions."""
    seed_path = tmp_path / "screen_questions.json"
    write_seed_file(seed_path, build_seed_payload(2, template_name="快速筛查 初始版"))

    with create_question_bank_schema() as session:
        service = QuestionBankSeedService(session)
        initial_summary = service.import_seed_files([seed_path])

        write_seed_file(
            seed_path, build_seed_payload(1, template_name="快速筛查 刷新版")
        )
        refresh_summary = service.import_seed_files([seed_path])

        template = session.scalar(
            select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == "SCREEN")
        )
        questions = session.scalars(
            select(QuestionBank)
            .where(QuestionBank.template_id == template.id)
            .order_by(QuestionBank.question_order)
        ).all()

    assert initial_summary.templates_created == 1
    assert initial_summary.questions_created == 2
    assert refresh_summary.templates_created == 0
    assert refresh_summary.templates_updated == 1
    assert refresh_summary.questions_created == 0
    assert refresh_summary.questions_updated == 1
    assert refresh_summary.questions_deleted == 1
    assert template is not None
    assert template.name == "快速筛查 刷新版"
    assert template.question_count == 1
    assert [question.question_code for question in questions] == ["SCREEN_01"]
    assert questions[0].question_text == "快速筛查 刷新版 第 1 题"
    assert questions[0].seed_source == "screen_questions.json"


def test_import_cli_initializes_database_with_database_url_override(
    tmp_path: Path,
) -> None:
    """The CLI should import committed seed files into an empty database file."""
    database_path = tmp_path / "question_bank_import.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    engine = create_engine(database_url)
    Base.metadata.create_all(
        engine,
        tables=[QuestionnaireTemplate.__table__, QuestionBank.__table__],
    )
    engine.dispose()

    exit_code = import_question_bank_main(
        [
            "--database-url",
            database_url,
            str(QUESTION_BANK_DIR),
        ]
    )

    engine = create_engine(database_url)
    with engine.connect() as connection:
        template_count = connection.execute(
            select(func.count()).select_from(QuestionnaireTemplate)
        ).scalar_one()
        question_count = connection.execute(
            select(func.count()).select_from(QuestionBank)
        ).scalar_one()
    engine.dispose()

    assert exit_code == 0
    assert template_count == 5
    assert question_count == 74
