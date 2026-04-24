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
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        table_names = inspect(connection).get_table_names()

    assert version == script.get_current_head()
    assert table_names == ["alembic_version"]

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

    assert "alembic_version" in table_names
    assert version is None

    engine.dispose()
