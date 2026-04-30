"""Repository helpers for administrator dashboard summary aggregates."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from src.constants.account_enums import StudentRiskStatus
from src.constants.treehole_enums import TreeholePublishStatus
from src.constants.workflow_enums import (
    AlertQueueStatus,
    FocusListStatus,
    ReviewPriority,
)
from src.models.alert_case import AlertCase
from src.models.focus_list_entry import FocusListEntry
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.models.student_user import StudentUser
from src.models.treehole_post import TreeholePost
from src.repositories.demo_visibility import exclude_seeded_students_clause


@dataclass(frozen=True, slots=True)
class DashboardSummaryCounts:
    """Flat aggregate counts consumed by the administrator dashboard."""

    pending_review_count: int
    open_high_risk_case_count: int
    confirmed_high_risk_count: int
    focus_student_count: int
    published_post_count: int
    highest_priority_pending_count: int
    blocked_post_count: int
    high_risk_student_count: int
    questionnaire_submission_count: int


class AdminDashboardRepository:
    """Load A02 dashboard counters from persisted workflow and content tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def load_summary_counts(
        self,
        *,
        show_seeded_cases: bool,
    ) -> DashboardSummaryCounts:
        """Return all counts required by the administrator overview page."""
        pending_review_statement = (
            select(func.count())
            .select_from(AlertCase)
            .where(AlertCase.queue_status == AlertQueueStatus.PENDING_REVIEW)
        )
        confirmed_high_risk_statement = (
            select(func.count())
            .select_from(AlertCase)
            .where(
                AlertCase.queue_status
                == AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION
            )
        )
        focus_student_statement = select(func.count(distinct(FocusListEntry.student_id))).where(
            FocusListEntry.status == FocusListStatus.ACTIVE
        )
        published_post_statement = (
            select(func.count())
            .select_from(TreeholePost)
            .where(TreeholePost.publish_status == TreeholePublishStatus.PUBLISHED)
        )
        highest_priority_pending_statement = (
            select(func.count())
            .select_from(AlertCase)
            .where(
                AlertCase.queue_status == AlertQueueStatus.PENDING_REVIEW,
                AlertCase.review_priority == ReviewPriority.HIGHEST,
            )
        )
        blocked_post_statement = (
            select(func.count())
            .select_from(TreeholePost)
            .where(
                TreeholePost.publish_status == TreeholePublishStatus.BLOCKED_HIGH_RISK
            )
        )
        high_risk_student_statement = (
            select(func.count())
            .select_from(StudentUser)
            .where(StudentUser.risk_status == StudentRiskStatus.HIGH)
        )
        questionnaire_submission_statement = select(func.count()).select_from(
            QuestionnaireSubmission
        )

        if not show_seeded_cases:
            pending_review_statement = pending_review_statement.where(
                exclude_seeded_students_clause(AlertCase.student_id)
            )
            confirmed_high_risk_statement = confirmed_high_risk_statement.where(
                exclude_seeded_students_clause(AlertCase.student_id)
            )
            focus_student_statement = focus_student_statement.where(
                exclude_seeded_students_clause(FocusListEntry.student_id)
            )
            published_post_statement = published_post_statement.where(
                exclude_seeded_students_clause(TreeholePost.student_id)
            )
            highest_priority_pending_statement = highest_priority_pending_statement.where(
                exclude_seeded_students_clause(AlertCase.student_id)
            )
            blocked_post_statement = blocked_post_statement.where(
                exclude_seeded_students_clause(TreeholePost.student_id)
            )
            high_risk_student_statement = high_risk_student_statement.where(
                exclude_seeded_students_clause(StudentUser.id)
            )
            questionnaire_submission_statement = questionnaire_submission_statement.where(
                exclude_seeded_students_clause(QuestionnaireSubmission.student_id)
            )

        pending_review_count = self._count(pending_review_statement)
        confirmed_high_risk_count = self._count(confirmed_high_risk_statement)
        focus_student_count = self._count(focus_student_statement)
        published_post_count = self._count(published_post_statement)
        highest_priority_pending_count = self._count(highest_priority_pending_statement)
        blocked_post_count = self._count(blocked_post_statement)
        high_risk_student_count = self._count(high_risk_student_statement)
        questionnaire_submission_count = self._count(questionnaire_submission_statement)

        return DashboardSummaryCounts(
            pending_review_count=pending_review_count,
            open_high_risk_case_count=(
                pending_review_count + confirmed_high_risk_count
            ),
            confirmed_high_risk_count=confirmed_high_risk_count,
            focus_student_count=focus_student_count,
            published_post_count=published_post_count,
            highest_priority_pending_count=highest_priority_pending_count,
            blocked_post_count=blocked_post_count,
            high_risk_student_count=high_risk_student_count,
            questionnaire_submission_count=questionnaire_submission_count,
        )

    def _count(self, statement) -> int:
        """Execute one aggregate count statement and normalize null results."""
        value = self.session.scalar(statement)
        return int(value or 0)
