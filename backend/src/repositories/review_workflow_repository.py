"""Repository helpers for alert-case and focus-list persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.alert_case import AlertCase
from src.models.focus_list_entry import FocusListEntry


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
