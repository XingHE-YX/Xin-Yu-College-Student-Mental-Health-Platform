"""Repository helpers for administrator user-directory queries."""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from src.constants.account_enums import StudentRiskStatus
from src.constants.workflow_enums import AlertQueueStatus, FocusListStatus
from src.models.alert_case import AlertCase
from src.models.audit_log import AuditLog
from src.models.focus_list_entry import FocusListEntry
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.models.student_user import StudentUser


class AdminUserDirectoryRepository:
    """Load masked student-directory rows and persist user-detail audit events."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_students(
        self,
        *,
        risk_status: StudentRiskStatus | None,
    ) -> list[StudentUser]:
        """Return students sorted by current risk severity and latest update time."""
        risk_order = case(
            (StudentUser.risk_status == StudentRiskStatus.HIGH, 0),
            (StudentUser.risk_status == StudentRiskStatus.WATCH, 1),
            else_=2,
        )
        statement = (
            select(StudentUser)
            .order_by(risk_order.asc(), StudentUser.updated_at.desc(), StudentUser.id.desc())
        )
        if risk_status is not None:
            statement = statement.where(StudentUser.risk_status == risk_status)
        return list(self.session.scalars(statement).all())

    def count_students_by_risk_status(self) -> dict[StudentRiskStatus, int]:
        """Return student counts grouped by aggregate risk status."""
        rows = self.session.execute(
            select(StudentUser.risk_status, func.count()).group_by(StudentUser.risk_status)
        ).all()
        return {risk_status: int(count) for risk_status, count in rows}

    def count_active_focus_entries_by_student(self) -> dict[int, int]:
        """Return active focus-entry counts keyed by student id."""
        rows = self.session.execute(
            select(StudentUser.id, func.count())
            .select_from(StudentUser)
            .join(FocusListEntry, FocusListEntry.student_id == StudentUser.id)
            .where(FocusListEntry.status == FocusListStatus.ACTIVE)
            .group_by(StudentUser.id)
        ).all()
        return {student_id: int(count) for student_id, count in rows}

    def count_open_alert_cases_by_student(self) -> dict[int, int]:
        """Return open alert-case counts keyed by student id."""
        open_statuses = (
            AlertQueueStatus.PENDING_REVIEW,
            AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
        )
        rows = self.session.execute(
            select(StudentUser.id, func.count())
            .select_from(StudentUser)
            .join(AlertCase, AlertCase.student_id == StudentUser.id)
            .where(AlertCase.queue_status.in_(open_statuses))
            .group_by(StudentUser.id)
        ).all()
        return {student_id: int(count) for student_id, count in rows}

    def get_student_detail(self, student_id: int) -> StudentUser | None:
        """Return one student with relationships required by the A06 detail pane."""
        statement = (
            select(StudentUser)
            .options(
                selectinload(StudentUser.questionnaire_submissions).selectinload(
                    QuestionnaireSubmission.template
                ),
                selectinload(StudentUser.treehole_posts),
                selectinload(StudentUser.alert_cases),
                selectinload(StudentUser.focus_list_entries),
            )
            .where(StudentUser.id == student_id)
        )
        return self.session.scalar(statement)

    def add_audit_log(self, audit_log: AuditLog) -> AuditLog:
        """Stage one audit event created by admin user-directory actions."""
        self.session.add(audit_log)
        self.session.flush()
        return audit_log
