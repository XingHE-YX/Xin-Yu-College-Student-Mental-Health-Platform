"""Repository helpers for administrator audit-log queries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.workflow_enums import AuditActorType
from src.models.audit_log import AuditLog
from src.repositories.demo_visibility import exclude_seeded_audit_logs_clause


class AdminAuditLogRepository:
    """Load filtered audit-log rows and distinct filter options for A07."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_logs(
        self,
        *,
        actor_type: AuditActorType | None,
        actor_id: int | None,
        action_code: str | None,
        target_type: str | None,
        created_from: datetime | None,
        created_to_exclusive: datetime | None,
        show_seeded_cases: bool,
    ) -> list[AuditLog]:
        """Return audit logs sorted newest-first under the requested filters."""
        statement = self._build_filtered_statement(
            actor_type=actor_type,
            actor_id=actor_id,
            action_code=action_code,
            target_type=target_type,
            created_from=created_from,
            created_to_exclusive=created_to_exclusive,
            show_seeded_cases=show_seeded_cases,
        ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        return list(self.session.scalars(statement).all())

    def list_distinct_action_codes(self, *, show_seeded_cases: bool) -> list[str]:
        """Return all action codes present in the audit table."""
        statement = (
            select(AuditLog.action_code)
            .distinct()
            .order_by(AuditLog.action_code.asc())
        )
        if not show_seeded_cases:
            statement = statement.where(exclude_seeded_audit_logs_clause())
        return [action_code for action_code in self.session.scalars(statement).all()]

    def list_distinct_target_types(self, *, show_seeded_cases: bool) -> list[str]:
        """Return all target types present in the audit table."""
        statement = (
            select(AuditLog.target_type)
            .distinct()
            .order_by(AuditLog.target_type.asc())
        )
        if not show_seeded_cases:
            statement = statement.where(exclude_seeded_audit_logs_clause())
        return [target_type for target_type in self.session.scalars(statement).all()]

    def list_distinct_actor_refs(
        self,
        *,
        show_seeded_cases: bool,
    ) -> list[tuple[AuditActorType, int | None]]:
        """Return all distinct `(actor_type, actor_id)` refs present in audit logs."""
        statement = (
            select(AuditLog.actor_type, AuditLog.actor_id)
            .distinct()
            .order_by(AuditLog.actor_type.asc(), AuditLog.actor_id.asc())
        )
        if not show_seeded_cases:
            statement = statement.where(exclude_seeded_audit_logs_clause())
        return list(self.session.execute(statement).all())

    def count_logs(
        self,
        *,
        actor_type: AuditActorType | None,
        actor_id: int | None,
        action_code: str | None,
        target_type: str | None,
        created_from: datetime | None,
        created_to_exclusive: datetime | None,
        show_seeded_cases: bool,
    ) -> int:
        """Return the filtered audit-log count."""
        statement = self._build_filtered_statement(
            actor_type=actor_type,
            actor_id=actor_id,
            action_code=action_code,
            target_type=target_type,
            created_from=created_from,
            created_to_exclusive=created_to_exclusive,
            show_seeded_cases=show_seeded_cases,
        )
        count_statement = select(func.count()).select_from(statement.subquery())
        value = self.session.scalar(count_statement)
        return int(value or 0)

    def _build_filtered_statement(
        self,
        *,
        actor_type: AuditActorType | None,
        actor_id: int | None,
        action_code: str | None,
        target_type: str | None,
        created_from: datetime | None,
        created_to_exclusive: datetime | None,
        show_seeded_cases: bool,
    ):
        """Build a filtered audit-log select statement shared by list/count queries."""
        statement = select(AuditLog)
        if actor_type is not None:
            statement = statement.where(AuditLog.actor_type == actor_type)
        if actor_id is not None:
            statement = statement.where(AuditLog.actor_id == actor_id)
        if action_code is not None:
            statement = statement.where(AuditLog.action_code == action_code)
        if target_type is not None:
            statement = statement.where(AuditLog.target_type == target_type)
        if created_from is not None:
            statement = statement.where(AuditLog.created_at >= created_from)
        if created_to_exclusive is not None:
            statement = statement.where(AuditLog.created_at < created_to_exclusive)
        if not show_seeded_cases:
            statement = statement.where(exclude_seeded_audit_logs_clause())
        return statement
