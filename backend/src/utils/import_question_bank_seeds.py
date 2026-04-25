"""CLI for importing questionnaire seed files into the database."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.database import (
    create_database_engine_from_url,
    create_session_factory,
    resolve_database_url,
)
from src.services.question_bank_seed_service import QuestionBankSeedService
from src.utils.validate_question_bank_seeds import (
    DEFAULT_SEED_DIRECTORY,
    resolve_input_paths,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for question-bank seed imports."""
    parser = argparse.ArgumentParser(
        description=(
            "Import questionnaire seed files into questionnaire_templates "
            "and question_bank."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "Specific seed files or directories to import. "
            "Defaults to appendices/question_bank."
        ),
    )
    parser.add_argument(
        "--database-url",
        dest="database_url",
        help="Optional database URL override. Defaults to DATABASE_URL / settings.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Import questionnaire seed files into the configured database."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    seed_paths = resolve_input_paths(args.paths)
    if not seed_paths:
        print(f"No question-bank seed JSON files found under {DEFAULT_SEED_DIRECTORY}.")
        return 0

    database_url = args.database_url or resolve_database_url()
    engine = create_database_engine_from_url(database_url)
    session_factory = create_session_factory(engine)

    try:
        with session_factory() as session:
            summary = QuestionBankSeedService(session).import_seed_files(seed_paths)
    finally:
        engine.dispose()

    print(
        "Imported question-bank seeds: "
        f"files={summary.seed_files_processed}, "
        f"templates_created={summary.templates_created}, "
        f"templates_updated={summary.templates_updated}, "
        f"questions_created={summary.questions_created}, "
        f"questions_updated={summary.questions_updated}, "
        f"questions_deleted={summary.questions_deleted}"
    )
    for seed_path in seed_paths:
        print(f"[OK] {Path(seed_path).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
