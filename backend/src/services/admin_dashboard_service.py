"""Service layer for administrator dashboard summary data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from src.models.base import utc_now
from src.repositories.admin_dashboard_repository import AdminDashboardRepository


@dataclass(frozen=True, slots=True)
class AdminDashboardKpiSnapshot:
    """Primary KPI counters shown at the top of the A02 dashboard."""

    pending_review_count: int
    open_high_risk_case_count: int
    confirmed_high_risk_count: int
    focus_student_count: int
    published_post_count: int


@dataclass(frozen=True, slots=True)
class AdminDashboardStatSnapshot:
    """Secondary stats that provide context for the next workflow steps."""

    highest_priority_pending_count: int
    blocked_post_count: int
    high_risk_student_count: int
    questionnaire_submission_count: int


@dataclass(frozen=True, slots=True)
class AdminDashboardSummarySnapshot:
    """Complete summary payload consumed by the Streamlit overview page."""

    generated_at: datetime
    kpis: AdminDashboardKpiSnapshot
    stats: AdminDashboardStatSnapshot


class AdminDashboardService:
    """Build the A02 administrator dashboard summary snapshot."""

    def __init__(self, session: Session) -> None:
        self.repository = AdminDashboardRepository(session)

    def build_summary(self) -> AdminDashboardSummarySnapshot:
        """Return the latest dashboard KPI snapshot from persisted data."""
        counts = self.repository.load_summary_counts()
        return AdminDashboardSummarySnapshot(
            generated_at=utc_now(),
            kpis=AdminDashboardKpiSnapshot(
                pending_review_count=counts.pending_review_count,
                open_high_risk_case_count=counts.open_high_risk_case_count,
                confirmed_high_risk_count=counts.confirmed_high_risk_count,
                focus_student_count=counts.focus_student_count,
                published_post_count=counts.published_post_count,
            ),
            stats=AdminDashboardStatSnapshot(
                highest_priority_pending_count=counts.highest_priority_pending_count,
                blocked_post_count=counts.blocked_post_count,
                high_risk_student_count=counts.high_risk_student_count,
                questionnaire_submission_count=counts.questionnaire_submission_count,
            ),
        )
