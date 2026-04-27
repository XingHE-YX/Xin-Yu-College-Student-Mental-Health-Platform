"""Repository helpers for alert-case and focus-list persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.alert_case import AlertCase
from src.models.audit_log import AuditLog
from src.models.focus_list_entry import FocusListEntry
from src.models.intervention_log import InterventionLog


class ReviewWorkflowRepository:
    """Persist review-workflow records created by automated risk decisions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_alert_case(self, alert_case: AlertCase) -> AlertCase:
        """Stage one alert-case row for persistence."""
        self.session.add(alert_case)
        self.session.flush()
        return alert_case

    def add_focus_list_entry(self, focus_entry: FocusListEntry) -> FocusListEntry:
        """Stage one focus-list row for persistence."""
        self.session.add(focus_entry)
        self.session.flush()
        return focus_entry

    def get_alert_case_by_id(self, alert_case_id: int) -> AlertCase | None:
        """Return one alert case by primary key."""
        statement = select(AlertCase).where(AlertCase.id == alert_case_id)
        return self.session.scalar(statement)

    def add_intervention_log(
        self,
        intervention_log: InterventionLog,
    ) -> InterventionLog:
        """Stage one intervention timeline row for persistence."""
        self.session.add(intervention_log)
        self.session.flush()
        return intervention_log

    def add_audit_log(self, audit_log: AuditLog) -> AuditLog:
        """Stage one audit-log row for persistence."""
        self.session.add(audit_log)
        self.session.flush()
        return audit_log
