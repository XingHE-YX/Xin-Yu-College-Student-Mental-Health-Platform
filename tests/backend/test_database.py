"""Tests for SQLAlchemy engine and session bootstrap."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.core.database import (
    check_database_connection,
    create_database_engine,
    create_session_factory,
    get_db_session,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import Base


def build_settings(
    *,
    app_env: str = "testing",
    database_url: str = "sqlite+pysqlite:///:memory:",
) -> Settings:
    """Create runtime settings for isolated database tests."""
    return Settings(
        APP_NAME="心语测试后端",
        APP_ENV=app_env,
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=database_url,
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=True,
    )


def test_create_database_engine_uses_configured_url() -> None:
    """The engine should honor the configured database URL and MySQL driver."""
    settings = build_settings(
        database_url="mysql+pymysql://demo:secret@127.0.0.1:3306/demo_db",
    )

    engine = create_database_engine(settings)

    assert engine.url.render_as_string(hide_password=False) == (
        "mysql+pymysql://demo:secret@127.0.0.1:3306/demo_db"
    )
    assert engine.dialect.name == "mysql"
    assert engine.url.drivername == "mysql+pymysql"

    engine.dispose()


def test_session_factory_and_connection_check_work() -> None:
    """The shared session factory should open working SQLAlchemy sessions."""
    engine = create_database_engine(build_settings())
    session_factory = create_session_factory(engine)

    check_database_connection(engine)

    with session_factory() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1

    engine.dispose()


def test_get_db_session_closes_session_after_use() -> None:
    """The request-scoped dependency should always close the session."""

    class FakeSession:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    fake_session = FakeSession()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                db_session_factory=lambda: fake_session,
            )
        )
    )

    session_generator = get_db_session(request)

    assert next(session_generator) is fake_session

    with pytest.raises(StopIteration):
        next(session_generator)

    assert fake_session.closed is True


def test_create_app_exposes_database_objects_on_app_state() -> None:
    """The FastAPI application should expose shared database infrastructure."""
    app = create_app(build_settings())

    assert app.state.db_engine.url.drivername == "sqlite+pysqlite"
    assert app.state.db_session_factory is not None
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"


def test_app_startup_checks_database_connection_outside_testing(
    monkeypatch,
) -> None:
    """Non-testing app startups should fail fast on unreachable databases."""
    captured: dict[str, object] = {}

    def fake_check_database_connection(engine) -> None:
        captured["engine"] = engine

    monkeypatch.setattr(
        "src.main.check_database_connection",
        fake_check_database_connection,
    )
    app = create_app(build_settings(app_env="development"))

    with TestClient(app):
        pass

    assert captured["engine"] is app.state.db_engine
