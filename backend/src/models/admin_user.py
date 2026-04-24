"""ORM model for administrator accounts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.account_enums import AdminRoleCode
from src.models.base import (
    DATETIME_3,
    MYSQL_TABLE_OPTIONS,
    Base,
    PrimaryKeyMixin,
    TimestampMixin,
    enum_values,
)


class AdminUser(PrimaryKeyMixin, TimestampMixin, Base):
    """Persist administrator authentication and role metadata."""

    __tablename__ = "admin_users"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_code: Mapped[AdminRoleCode] = mapped_column(
        Enum(
            AdminRoleCode,
            name="admin_role_code_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DATETIME_3, nullable=True)
