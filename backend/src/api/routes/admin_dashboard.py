"""Administrator dashboard summary routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.core.auth import get_current_admin
from src.core.database import get_db_session
from src.models.admin_user import AdminUser
from src.schemas.admin_dashboard import (
    AdminDashboardKpiResponse,
    AdminDashboardStatResponse,
    AdminDashboardSummaryData,
    AdminDashboardSummaryResponse,
    AdminDashboardSummarySuccessResponse,
)
from src.services.admin_dashboard_service import AdminDashboardService

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


def build_request_id() -> str:
    """Return a short opaque request identifier for API envelopes."""
    return uuid4().hex


@router.get(
    "/summary",
    response_model=AdminDashboardSummarySuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_admin_dashboard_summary(
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminDashboardSummarySuccessResponse:
    """Return the authenticated administrator overview KPI snapshot."""
    summary = AdminDashboardService(session).build_summary()
    return AdminDashboardSummarySuccessResponse(
        request_id=build_request_id(),
        data=AdminDashboardSummaryData(
            summary=AdminDashboardSummaryResponse(
                generated_at=summary.generated_at,
                kpis=AdminDashboardKpiResponse(
                    pending_review_count=summary.kpis.pending_review_count,
                    open_high_risk_case_count=summary.kpis.open_high_risk_case_count,
                    confirmed_high_risk_count=summary.kpis.confirmed_high_risk_count,
                    focus_student_count=summary.kpis.focus_student_count,
                    published_post_count=summary.kpis.published_post_count,
                ),
                stats=AdminDashboardStatResponse(
                    highest_priority_pending_count=(
                        summary.stats.highest_priority_pending_count
                    ),
                    blocked_post_count=summary.stats.blocked_post_count,
                    high_risk_student_count=summary.stats.high_risk_student_count,
                    questionnaire_submission_count=(
                        summary.stats.questionnaire_submission_count
                    ),
                ),
            )
        ),
    )
