"""Administrator analytics routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.core.auth import get_current_admin
from src.core.database import get_db_session
from src.models.admin_user import AdminUser
from src.schemas.admin_analytics import (
    AdminAnalyticsAlertProcessingItemResponse,
    AdminAnalyticsAlertProcessingResponse,
    AdminAnalyticsDailyTrendItemResponse,
    AdminAnalyticsDailyTrendResponse,
    AdminAnalyticsData,
    AdminAnalyticsResponse,
    AdminAnalyticsRiskDistributionItemResponse,
    AdminAnalyticsRiskDistributionResponse,
    AdminAnalyticsSuccessResponse,
)
from src.services.admin_analytics_service import AdminAnalyticsService

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


def build_request_id() -> str:
    """Return a short opaque request identifier for API envelopes."""
    return uuid4().hex


@router.get(
    "/trends",
    response_model=AdminAnalyticsSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_admin_analytics_trends(
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminAnalyticsSuccessResponse:
    """Return chart-ready analytics aggregates for the authenticated admin."""
    analytics = AdminAnalyticsService(session).build_trends_snapshot()
    return AdminAnalyticsSuccessResponse(
        request_id=build_request_id(),
        data=AdminAnalyticsData(
            analytics=AdminAnalyticsResponse(
                generated_at=analytics.generated_at,
                risk_distribution=AdminAnalyticsRiskDistributionResponse(
                    total_students=analytics.risk_distribution.total_students,
                    items=[
                        AdminAnalyticsRiskDistributionItemResponse(
                            risk_status=item.risk_status,
                            student_count=item.student_count,
                        )
                        for item in analytics.risk_distribution.items
                    ],
                ),
                daily_trends=AdminAnalyticsDailyTrendResponse(
                    window_days=analytics.daily_trends.window_days,
                    start_date=analytics.daily_trends.start_date,
                    end_date=analytics.daily_trends.end_date,
                    items=[
                        AdminAnalyticsDailyTrendItemResponse(
                            date=item.date,
                            questionnaire_submission_count=(
                                item.questionnaire_submission_count
                            ),
                            treehole_post_count=item.treehole_post_count,
                            alert_case_count=item.alert_case_count,
                        )
                        for item in analytics.daily_trends.items
                    ],
                ),
                alert_processing=AdminAnalyticsAlertProcessingResponse(
                    total_alert_case_count=(
                        analytics.alert_processing.total_alert_case_count
                    ),
                    items=[
                        AdminAnalyticsAlertProcessingItemResponse(
                            queue_status=item.queue_status,
                            case_count=item.case_count,
                        )
                        for item in analytics.alert_processing.items
                    ],
                ),
            )
        ),
    )
