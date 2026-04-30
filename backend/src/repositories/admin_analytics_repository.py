"""Repository helpers for administrator analytics aggregates."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.account_enums import StudentRiskStatus
from src.constants.workflow_enums import AlertQueueStatus
from src.models.alert_case import AlertCase
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.models.student_user import StudentUser
from src.models.treehole_post import TreeholePost
from src.repositories.demo_visibility import exclude_seeded_students_clause


class AdminAnalyticsRepository:
    """Load chart-ready aggregate inputs for the administrator analytics page."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def load_student_risk_distribution(
        self,
        *,
        show_seeded_cases: bool,
    ) -> dict[StudentRiskStatus, int]:
        """Return student counts grouped by the current aggregate risk state."""
        statement = (
            select(StudentUser.risk_status, func.count())
            .select_from(StudentUser)
            .group_by(StudentUser.risk_status)
        )
        if not show_seeded_cases:
            statement = statement.where(exclude_seeded_students_clause(StudentUser.id))
        rows = self.session.execute(statement).all()
        return {
            risk_status: int(count or 0)
            for risk_status, count in rows
            if risk_status is not None
        }

    def load_alert_queue_status_counts(
        self,
        *,
        show_seeded_cases: bool,
    ) -> dict[AlertQueueStatus, int]:
        """Return alert-case counts grouped by their current workflow status."""
        statement = (
            select(AlertCase.queue_status, func.count())
            .select_from(AlertCase)
            .group_by(AlertCase.queue_status)
        )
        if not show_seeded_cases:
            statement = statement.where(
                exclude_seeded_students_clause(AlertCase.student_id)
            )
        rows = self.session.execute(statement).all()
        return {
            queue_status: int(count or 0)
            for queue_status, count in rows
            if queue_status is not None
        }

    def load_questionnaire_submission_dates(
        self,
        *,
        start_at: datetime,
        end_before: datetime,
        show_seeded_cases: bool,
    ) -> list[date]:
        """Return submission dates for questionnaire activity within the window."""
        statement = select(QuestionnaireSubmission.submitted_at).where(
            QuestionnaireSubmission.submitted_at >= start_at,
            QuestionnaireSubmission.submitted_at < end_before,
        )
        if not show_seeded_cases:
            statement = statement.where(
                exclude_seeded_students_clause(QuestionnaireSubmission.student_id)
            )
        return self._load_date_list(statement)

    def load_treehole_post_dates(
        self,
        *,
        start_at: datetime,
        end_before: datetime,
        show_seeded_cases: bool,
    ) -> list[date]:
        """Return created dates for treehole activity within the window."""
        statement = select(TreeholePost.created_at).where(
            TreeholePost.created_at >= start_at,
            TreeholePost.created_at < end_before,
        )
        if not show_seeded_cases:
            statement = statement.where(
                exclude_seeded_students_clause(TreeholePost.student_id)
            )
        return self._load_date_list(statement)

    def load_alert_case_dates(
        self,
        *,
        start_at: datetime,
        end_before: datetime,
        show_seeded_cases: bool,
    ) -> list[date]:
        """Return created dates for alert-case activity within the window."""
        statement = select(AlertCase.created_at).where(
            AlertCase.created_at >= start_at,
            AlertCase.created_at < end_before,
        )
        if not show_seeded_cases:
            statement = statement.where(
                exclude_seeded_students_clause(AlertCase.student_id)
            )
        return self._load_date_list(statement)

    def _load_date_list(self, statement) -> list[date]:
        """Normalize one scalar datetime query into calendar-date values."""
        timestamps = self.session.scalars(statement).all()
        return [timestamp.date() for timestamp in timestamps if timestamp is not None]
