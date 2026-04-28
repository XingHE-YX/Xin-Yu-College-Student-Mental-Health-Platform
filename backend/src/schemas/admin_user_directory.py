"""Request and response schemas for administrator user-directory APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.constants.account_enums import StudentRiskStatus


class AdminStudentListItemResponse(BaseModel):
    """Compact student row returned by `GET /api/v1/admin/users`."""

    model_config = ConfigDict(extra="forbid")

    student_id: int
    student_label: str
    masked_phone: str
    college_name: str
    class_name: str
    risk_status: str
    consent_status: str
    active_focus_count: int
    open_alert_count: int
    last_login_at: datetime | None
    updated_at: datetime


class AdminStudentRiskStatusCountResponse(BaseModel):
    """One risk-status count bucket for the A06 filter controls."""

    model_config = ConfigDict(extra="forbid")

    risk_status: StudentRiskStatus
    count: int


class AdminStudentListData(BaseModel):
    """Data payload returned by `GET /api/v1/admin/users`."""

    model_config = ConfigDict(extra="forbid")

    applied_risk_status: StudentRiskStatus | None
    status_counts: list[AdminStudentRiskStatusCountResponse]
    items: list[AdminStudentListItemResponse]


class AdminStudentListSuccessResponse(BaseModel):
    """Standard success envelope for administrator user-directory list responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminStudentListData


class AdminStudentDetailData(BaseModel):
    """Data payload returned by `GET /api/v1/admin/users/{student_id}`."""

    model_config = ConfigDict(extra="forbid")

    student: dict[str, Any]


class AdminStudentDetailSuccessResponse(BaseModel):
    """Standard success envelope for admin student detail responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminStudentDetailData


class AdminStudentRevealPhoneData(BaseModel):
    """Data payload returned after explicitly revealing the student's full phone."""

    model_config = ConfigDict(extra="forbid")

    student_id: int
    full_phone: str


class AdminStudentRevealPhoneSuccessResponse(BaseModel):
    """Standard success envelope for full-phone reveal responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminStudentRevealPhoneData
