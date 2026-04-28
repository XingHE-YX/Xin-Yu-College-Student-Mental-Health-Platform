"""Repository helpers for administrator alert queue and detail queries."""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.workflow_enums import AlertQueueStatus, ReviewPriority
from src.models.alert_case import AlertCase
from src.models.audit_log import AuditLog
from src.models.intervention_log import InterventionLog
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.models.treehole_post import TreeholePost


class AdminAlertRepository:
    """Load alert queue rows, detail relationships, and audit events for admins."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_alert_cases(
        self,
        *,
        queue_status: AlertQueueStatus | None,
    ) -> list[AlertCase]:
        """Return alert cases sorted by priority then newest-first within each priority."""
        priority_order = case(
            (AlertCase.review_priority == ReviewPriority.HIGHEST, 0),
            (AlertCase.review_priority == ReviewPriority.URGENT, 1),
            else_=2,
        )
        statement = (
            select(AlertCase)
            .options(
                selectinload(AlertCase.student),
                selectinload(AlertCase.reviewer),
                selectinload(AlertCase.source_post),
                selectinload(AlertCase.source_submission).selectinload(
                    QuestionnaireSubmission.template
                ),
            )
            .order_by(priority_order.asc(), AlertCase.created_at.desc(), AlertCase.id.desc())
        )
        if queue_status is not None:
            statement = statement.where(AlertCase.queue_status == queue_status)
        return list(self.session.scalars(statement).all())

    def count_alert_cases_by_status(self) -> dict[AlertQueueStatus, int]:
        """Return alert-case counts grouped by workflow status."""
        rows = self.session.execute(
            select(AlertCase.queue_status, func.count())
            .group_by(AlertCase.queue_status)
        ).all()
        return {queue_status: int(count) for queue_status, count in rows}

    def get_alert_case_detail(self, alert_case_id: int) -> AlertCase | None:
        """Return one alert case with all relationships needed by the A04 detail page."""
        statement = (
            select(AlertCase)
            .options(
                selectinload(AlertCase.student),
                selectinload(AlertCase.reviewer),
                selectinload(AlertCase.source_post).selectinload(
                    TreeholePost.ai_analysis_records
                ),
                selectinload(AlertCase.source_submission).selectinload(
                    QuestionnaireSubmission.template
                ),
                selectinload(AlertCase.intervention_logs).selectinload(
                    InterventionLog.admin_user
                ),
            )
            .where(AlertCase.id == alert_case_id)
        )
        return self.session.scalar(statement)

    def list_student_submissions(
        self,
        *,
        student_id: int,
    ) -> list[QuestionnaireSubmission]:
        """Return student questionnaire submissions newest-first with template metadata."""
        statement = (
            select(QuestionnaireSubmission)
            .options(selectinload(QuestionnaireSubmission.template))
            .where(QuestionnaireSubmission.student_id == student_id)
            .order_by(
                QuestionnaireSubmission.submitted_at.desc(),
                QuestionnaireSubmission.id.desc(),
            )
        )
        return list(self.session.scalars(statement).all())

    def has_other_high_risk_submission(
        self,
        *,
        student_id: int,
        exclude_submission_id: int | None,
    ) -> bool:
        """Return whether the student has another high-risk questionnaire submission."""
        statement = select(func.count()).select_from(QuestionnaireSubmission).where(
            QuestionnaireSubmission.student_id == student_id,
            QuestionnaireSubmission.risk_level == QuestionnaireRiskLevel.HIGH,
        )
        if exclude_submission_id is not None:
            statement = statement.where(
                QuestionnaireSubmission.id != exclude_submission_id
            )
        return bool(self.session.scalar(statement))

    def has_other_high_risk_treehole_post(
        self,
        *,
        student_id: int,
        exclude_post_id: int | None,
    ) -> bool:
        """Return whether the student has another high-risk treehole post record."""
        statement = select(func.count()).select_from(TreeholePost).where(
            TreeholePost.student_id == student_id,
            TreeholePost.risk_level == QuestionnaireRiskLevel.HIGH,
        )
        if exclude_post_id is not None:
            statement = statement.where(TreeholePost.id != exclude_post_id)
        return bool(self.session.scalar(statement))

    def add_audit_log(self, audit_log: AuditLog) -> AuditLog:
        """Stage one audit event created by alert detail or reveal views."""
        self.session.add(audit_log)
        self.session.flush()
        return audit_log
