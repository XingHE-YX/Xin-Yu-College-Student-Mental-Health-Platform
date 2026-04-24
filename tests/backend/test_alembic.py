"""Tests for Alembic migration configuration and execution."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def build_alembic_config() -> Config:
    """Create an Alembic config bound to the repository backend directory."""
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def test_alembic_upgrade_head_applies_current_revision(
    tmp_path,
    monkeypatch,
) -> None:
    """The configured Alembic environment should upgrade an empty database to head."""
    database_path = tmp_path / "alembic_upgrade.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = build_alembic_config()
    script = ScriptDirectory.from_config(config)

    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        inspector = inspect(connection)
        table_names = inspector.get_table_names()
        student_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("student_users")
        }
        admin_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("admin_users")
        }
        template_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("questionnaire_templates")
        }
        question_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("question_bank")
        }
        consent_foreign_keys = inspector.get_foreign_keys("consent_records")
        submission_foreign_keys = inspector.get_foreign_keys("questionnaire_submissions")
        answer_foreign_keys = inspector.get_foreign_keys("questionnaire_answers")
        report_foreign_keys = inspector.get_foreign_keys("assessment_reports")

    assert version == script.get_current_head()
    assert sorted(table_names) == [
        "admin_users",
        "alembic_version",
        "assessment_reports",
        "consent_records",
        "question_bank",
        "questionnaire_answers",
        "questionnaire_submissions",
        "questionnaire_templates",
        "student_users",
    ]
    assert ("phone_e164",) in student_unique_constraints
    assert ("wechat_openid",) in student_unique_constraints
    assert ("username",) in admin_unique_constraints
    assert ("code",) in template_unique_constraints
    assert ("question_code",) in question_unique_constraints
    assert consent_foreign_keys[0]["referred_table"] == "student_users"
    assert consent_foreign_keys[0]["constrained_columns"] == ["student_id"]
    assert sorted(foreign_key["referred_table"] for foreign_key in submission_foreign_keys) == [
        "questionnaire_templates",
        "student_users",
    ]
    assert sorted(foreign_key["referred_table"] for foreign_key in answer_foreign_keys) == [
        "question_bank",
        "questionnaire_submissions",
    ]
    assert report_foreign_keys[0]["referred_table"] == "student_users"

    engine.dispose()


def test_alembic_downgrade_base_removes_version_table(
    tmp_path,
    monkeypatch,
) -> None:
    """The initial empty migration should cleanly downgrade back to base."""
    database_path = tmp_path / "alembic_downgrade.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = build_alembic_config()

    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
        table_names = inspect(connection).get_table_names()

    assert table_names == ["alembic_version"]
    assert version is None

    engine.dispose()
