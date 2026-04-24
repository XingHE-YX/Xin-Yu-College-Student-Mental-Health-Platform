"""SQLAlchemy engine and session management for the backend."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.settings import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Create a shared SQLAlchemy engine from runtime settings."""
    engine_kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

    if settings.database_url.startswith("mysql"):
        engine_kwargs["connect_args"] = {"charset": "utf8mb4"}

    return create_engine(settings.database_url, **engine_kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the application's shared session factory."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


def check_database_connection(engine: Engine) -> None:
    """Verify that the configured database accepts connections."""
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Yield a request-scoped database session and close it afterwards."""
    session_factory: sessionmaker[Session] = request.app.state.db_session_factory
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
