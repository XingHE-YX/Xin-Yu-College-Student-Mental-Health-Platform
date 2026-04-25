"""ORM model for audit trail entries."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.workflow_enums import AuditActorType
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    PrimaryKeyMixin,
    enum_values,
)


class AuditLog(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist sensitive-operation audit events."""

    __tablename__ = "audit_logs"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    actor_type: Mapped[AuditActorType] = mapped_column(
        Enum(
            AuditActorType,
            name="audit_actor_type_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    actor_id: Mapped[int | None] = mapped_column(BIGINT_PRIMARY_KEY, nullable=True)
    action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[int | None] = mapped_column(BIGINT_PRIMARY_KEY, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
