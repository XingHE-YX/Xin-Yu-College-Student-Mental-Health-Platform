"""SQLAlchemy engine and session management for the backend."""

from __future__ import annotations

import os
from collections.abc import Generator

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.settings import Settings, get_settings


def resolve_database_url(default: str | None = None) -> str:
    """Resolve the database URL for runtime code and migration commands."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    try:
        return get_settings().database_url
    except ValidationError:
        if default is None:
            raise
        return default


def create_database_engine_from_url(database_url: str) -> Engine:
    """Create a shared SQLAlchemy engine from a database URL."""
    engine_kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }

    if database_url.startswith("mysql"):
        engine_kwargs["connect_args"] = {"charset": "utf8mb4"}

    return create_engine(database_url, **engine_kwargs)


def create_database_engine(settings: Settings) -> Engine:
    """Create a shared SQLAlchemy engine from runtime settings."""
    return create_database_engine_from_url(settings.database_url)


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
