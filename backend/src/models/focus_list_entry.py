"""ORM model for watch-level focus list entries."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.workflow_enums import CaseSourceType, FocusListStatus
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    DATETIME_3,
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    PrimaryKeyMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.student_user import StudentUser


class FocusListEntry(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist entries in the administrative watch-list."""

    __tablename__ = "focus_list_entries"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    student_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("student_users.id"),
        nullable=False,
    )
    source_type: Mapped[CaseSourceType] = mapped_column(
        Enum(
            CaseSourceType,
            name="focus_source_type_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    source_id: Mapped[int] = mapped_column(BIGINT_PRIMARY_KEY, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[FocusListStatus] = mapped_column(
        Enum(
            FocusListStatus,
            name="focus_list_status_enum",
            values_callable=enum_values,
        ),
        default=FocusListStatus.ACTIVE,
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DATETIME_3, nullable=True)

    student: Mapped[StudentUser] = relationship(back_populates="focus_list_entries")
