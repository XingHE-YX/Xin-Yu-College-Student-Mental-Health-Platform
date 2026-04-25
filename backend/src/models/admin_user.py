"""ORM model for administrator accounts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.account_enums import AdminRoleCode
from src.models.base import (
    DATETIME_3,
    MYSQL_TABLE_OPTIONS,
    Base,
    PrimaryKeyMixin,
    TimestampMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.alert_case import AlertCase
    from src.models.intervention_log import InterventionLog


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

    reviewed_alert_cases: Mapped[list[AlertCase]] = relationship(
        back_populates="reviewer"
    )
    intervention_logs: Mapped[list[InterventionLog]] = relationship(
        back_populates="admin_user"
    )
