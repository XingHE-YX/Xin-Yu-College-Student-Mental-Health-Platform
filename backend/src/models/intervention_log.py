"""ORM model for intervention timeline entries on alert cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.workflow_enums import InterventionActionType
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    PrimaryKeyMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.admin_user import AdminUser
    from src.models.alert_case import AlertCase


class InterventionLog(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist each manual intervention action taken on an alert case."""

    __tablename__ = "intervention_logs"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    alert_case_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("alert_cases.id"),
        nullable=False,
    )
    admin_user_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("admin_users.id"),
        nullable=False,
    )
    action_type: Mapped[InterventionActionType] = mapped_column(
        Enum(
            InterventionActionType,
            name="intervention_action_type_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    action_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    alert_case: Mapped[AlertCase] = relationship(back_populates="intervention_logs")
    admin_user: Mapped[AdminUser] = relationship(back_populates="intervention_logs")
