"""Response schemas for administrator dashboard summary APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AdminDashboardKpiResponse(BaseModel):
    """Primary KPI counters returned by `GET /api/v1/admin/dashboard/summary`."""

    model_config = ConfigDict(extra="forbid")

    pending_review_count: int
    open_high_risk_case_count: int
    confirmed_high_risk_count: int
    focus_student_count: int
    published_post_count: int


class AdminDashboardStatResponse(BaseModel):
    """Secondary operational counters rendered below the main KPI row."""

    model_config = ConfigDict(extra="forbid")

    highest_priority_pending_count: int
    blocked_post_count: int
    high_risk_student_count: int
    questionnaire_submission_count: int


class AdminDashboardSummaryResponse(BaseModel):
    """Serializable A02 dashboard summary payload."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    kpis: AdminDashboardKpiResponse
    stats: AdminDashboardStatResponse


class AdminDashboardSummaryData(BaseModel):
    """Data envelope returned by the administrator dashboard summary route."""

    model_config = ConfigDict(extra="forbid")

    summary: AdminDashboardSummaryResponse


class AdminDashboardSummarySuccessResponse(BaseModel):
    """Standard success envelope for administrator dashboard summary responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminDashboardSummaryData
