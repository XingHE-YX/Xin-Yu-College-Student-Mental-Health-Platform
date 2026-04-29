"""Response schemas for administrator analytics APIs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.constants.account_enums import StudentRiskStatus
from src.constants.workflow_enums import AlertQueueStatus


class AdminAnalyticsRiskDistributionItemResponse(BaseModel):
    """One serialized bucket in the student risk-distribution chart."""

    model_config = ConfigDict(extra="forbid")

    risk_status: StudentRiskStatus
    student_count: int


class AdminAnalyticsRiskDistributionResponse(BaseModel):
    """Serializable student risk-distribution payload."""

    model_config = ConfigDict(extra="forbid")

    total_students: int
    items: list[AdminAnalyticsRiskDistributionItemResponse]


class AdminAnalyticsDailyTrendItemResponse(BaseModel):
    """One serialized day in the recent-activity trend series."""

    model_config = ConfigDict(extra="forbid")

    date: date
    questionnaire_submission_count: int
    treehole_post_count: int
    alert_case_count: int


class AdminAnalyticsDailyTrendResponse(BaseModel):
    """Serializable fixed-window activity trend payload."""

    model_config = ConfigDict(extra="forbid")

    window_days: int
    start_date: date
    end_date: date
    items: list[AdminAnalyticsDailyTrendItemResponse]


class AdminAnalyticsAlertProcessingItemResponse(BaseModel):
    """One serialized bucket in the alert-case status summary."""

    model_config = ConfigDict(extra="forbid")

    queue_status: AlertQueueStatus
    case_count: int


class AdminAnalyticsAlertProcessingResponse(BaseModel):
    """Serializable alert workflow status summary."""

    model_config = ConfigDict(extra="forbid")

    total_alert_case_count: int
    items: list[AdminAnalyticsAlertProcessingItemResponse]


class AdminAnalyticsResponse(BaseModel):
    """Serializable analytics snapshot consumed by the admin chart page."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    risk_distribution: AdminAnalyticsRiskDistributionResponse
    daily_trends: AdminAnalyticsDailyTrendResponse
    alert_processing: AdminAnalyticsAlertProcessingResponse


class AdminAnalyticsData(BaseModel):
    """Data envelope returned by the administrator analytics route."""

    model_config = ConfigDict(extra="forbid")

    analytics: AdminAnalyticsResponse


class AdminAnalyticsSuccessResponse(BaseModel):
    """Standard success envelope for administrator analytics responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminAnalyticsData
