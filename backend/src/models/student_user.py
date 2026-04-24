"""ORM model for student user accounts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.account_enums import ConsentStatus, StudentRiskStatus
from src.models.base import (
    DATETIME_3,
    MYSQL_TABLE_OPTIONS,
    Base,
    PrimaryKeyMixin,
    TimestampMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.consent_record import ConsentRecord


class StudentUser(PrimaryKeyMixin, TimestampMixin, Base):
    """Persist the student-side account identity and consent state."""

    __tablename__ = "student_users"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    display_nickname: Mapped[str] = mapped_column(String(32), nullable=False)
    display_avatar_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    college_name: Mapped[str] = mapped_column(String(64), nullable=False)
    class_name: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_status: Mapped[StudentRiskStatus] = mapped_column(
        Enum(
            StudentRiskStatus,
            name="student_risk_status_enum",
            values_callable=enum_values,
        ),
        default=StudentRiskStatus.NORMAL,
        nullable=False,
    )
    consent_status: Mapped[ConsentStatus] = mapped_column(
        Enum(
            ConsentStatus,
            name="student_consent_status_enum",
            values_callable=enum_values,
        ),
        default=ConsentStatus.MISSING,
        nullable=False,
    )
    is_demo: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DATETIME_3, nullable=True)

    consent_records: Mapped[list[ConsentRecord]] = relationship(back_populates="student")
