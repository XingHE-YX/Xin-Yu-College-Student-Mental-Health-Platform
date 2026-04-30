"""CLI for preparing deterministic demo data required by IMPLEMENTATION_PLAN 14.1."""

from __future__ import annotations

import argparse

from src.core.database import (
    create_database_engine_from_url,
    create_session_factory,
    resolve_database_url,
)
from src.services.demo_seed_service import (
    DEMO_ADMIN_PASSWORD,
    DemoSeedService,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the demo dataset seed command."""
    parser = argparse.ArgumentParser(
        description=(
            "Seed one deterministic demo dataset containing low/watch/high students, "
            "treehole posts, alerts, focus entries, and audit examples."
        ),
    )
    parser.add_argument(
        "--database-url",
        dest="database_url",
        help="Optional database URL override. Defaults to DATABASE_URL / settings.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Seed the configured database with the deterministic 14.1 demo dataset."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    database_url = args.database_url or resolve_database_url()
    engine = create_database_engine_from_url(database_url)
    session_factory = create_session_factory(engine)

    try:
        with session_factory() as session:
            summary = DemoSeedService(session).seed_demo_dataset()
    finally:
        engine.dispose()

    print(
        "Seeded demo dataset: "
        f"students={summary.students_seeded}, "
        f"submissions={summary.questionnaire_submissions_seeded}, "
        f"posts={summary.posts_seeded}, "
        f"reactions={summary.reactions_seeded}, "
        f"alerts={summary.alerts_seeded}, "
        f"focus_entries={summary.focus_entries_seeded}, "
        f"intervention_logs={summary.intervention_logs_seeded}, "
        f"audit_logs={summary.audit_logs_seeded}"
    )
    if summary.admin_created:
        print(
            "Created default admin account: "
            f"{summary.admin_username} / {DEMO_ADMIN_PASSWORD}"
        )
    else:
        print(
            "Default admin account already existed: "
            f"{summary.admin_username}"
        )
    print(
        "Question-bank import: "
        f"files={summary.question_bank_import.seed_files_processed}, "
        f"templates_created={summary.question_bank_import.templates_created}, "
        f"templates_updated={summary.question_bank_import.templates_updated}, "
        f"questions_created={summary.question_bank_import.questions_created}, "
        f"questions_updated={summary.question_bank_import.questions_updated}, "
        f"questions_deleted={summary.question_bank_import.questions_deleted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
