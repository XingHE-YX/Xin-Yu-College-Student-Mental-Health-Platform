"""ORM model for immutable student consent decisions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.account_enums import ConsentType
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    DATETIME_3,
    MYSQL_TABLE_OPTIONS,
    Base,
    PrimaryKeyMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.student_user import StudentUser


class ConsentRecord(PrimaryKeyMixin, Base):
    """Persist immutable privacy and crisis-intervention consent decisions."""

    __tablename__ = "consent_records"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    student_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("student_users.id"),
        nullable=False,
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(
            ConsentType,
            name="consent_type_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    consent_version: Mapped[str] = mapped_column(String(16), nullable=False)
    granted: Mapped[bool] = mapped_column(nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DATETIME_3, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    student: Mapped[StudentUser] = relationship(back_populates="consent_records")
