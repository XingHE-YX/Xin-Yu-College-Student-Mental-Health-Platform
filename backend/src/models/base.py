"""Shared SQLAlchemy declarative base configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, Integer, MetaData
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

MYSQL_TABLE_OPTIONS = {
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}

BIGINT_PRIMARY_KEY = Integer().with_variant(
    mysql.BIGINT(unsigned=True),
    "mysql",
)
DATETIME_3 = DateTime(timezone=False).with_variant(
    mysql.DATETIME(fsp=3),
    "mysql",
)


def enum_values(enum_class: type[Enum]) -> list[str]:
    """Return enum values in declaration order for SQLAlchemy Enum columns."""
    return [member.value for member in enum_class]


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime for storage."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Base class for all ORM models in the project."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class PrimaryKeyMixin:
    """Provide a shared unsigned BIGINT primary key."""

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
        autoincrement=True,
    )


class TimestampMixin:
    """Provide shared UTC timestamp columns used by mutable tables."""

    created_at: Mapped[datetime] = mapped_column(
        DATETIME_3,
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME_3,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
