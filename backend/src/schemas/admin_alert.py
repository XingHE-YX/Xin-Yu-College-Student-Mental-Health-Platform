"""Request and response schemas for administrator alert queue APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.constants.workflow_enums import AlertQueueStatus, ReviewPriority


class AdminAlertListItemResponse(BaseModel):
    """Compact queue row returned by `GET /api/v1/admin/alerts`."""

    model_config = ConfigDict(extra="forbid")

    alert_id: int
    created_at: datetime
    queue_status: AlertQueueStatus
    review_priority: ReviewPriority
    case_level: str
    source_type: str
    source_label: str
    source_preview: str
    student_label: str
    masked_phone: str
    college_name: str
    class_name: str
    risk_status: str
    reviewer_display_name: str | None
    reviewed_at: datetime | None


class AdminAlertQueueStatusCountResponse(BaseModel):
    """One queue-status count bucket for the A03 filter controls."""

    model_config = ConfigDict(extra="forbid")

    queue_status: AlertQueueStatus
    count: int


class AdminAlertListData(BaseModel):
    """Data payload returned by `GET /api/v1/admin/alerts`."""

    model_config = ConfigDict(extra="forbid")

    applied_queue_status: AlertQueueStatus | None
    status_counts: list[AdminAlertQueueStatusCountResponse]
    items: list[AdminAlertListItemResponse]


class AdminAlertListSuccessResponse(BaseModel):
    """Standard success envelope for alert queue list responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminAlertListData


class AdminAlertDetailData(BaseModel):
    """Data payload returned by `GET /api/v1/admin/alerts/{alert_id}`."""

    model_config = ConfigDict(extra="forbid")

    alert: dict[str, Any]


class AdminAlertDetailSuccessResponse(BaseModel):
    """Standard success envelope for alert detail responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminAlertDetailData


class AdminAlertRevealContentData(BaseModel):
    """Data payload returned after explicitly revealing treehole raw content."""

    model_config = ConfigDict(extra="forbid")

    alert_id: int
    source_type: str
    full_content: str


class AdminAlertRevealContentSuccessResponse(BaseModel):
    """Standard success envelope for raw-content reveal responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminAlertRevealContentData


class AdminAlertConfirmRequest(BaseModel):
    """Payload for `POST /api/v1/admin/alerts/{alert_id}/confirm`."""

    model_config = ConfigDict(extra="forbid")

    review_note: str = Field(min_length=1)
    intervention_note: str = Field(min_length=1)


class AdminAlertDismissRequest(BaseModel):
    """Payload for `POST /api/v1/admin/alerts/{alert_id}/dismiss`."""

    model_config = ConfigDict(extra="forbid")

    review_note: str = Field(min_length=1)


class AdminAlertCloseRequest(BaseModel):
    """Payload for `POST /api/v1/admin/alerts/{alert_id}/close`."""

    model_config = ConfigDict(extra="forbid")

    action_note: str = Field(min_length=1)


class AdminAlertAddNoteRequest(BaseModel):
    """Payload for `POST /api/v1/admin/alerts/{alert_id}/notes`."""

    model_config = ConfigDict(extra="forbid")

    action_note: str = Field(min_length=1)


class AdminAlertActionData(BaseModel):
    """Action payload shared by confirm, dismiss, close, and note responses."""

    model_config = ConfigDict(extra="forbid")

    alert_id: int
    queue_status: AlertQueueStatus
    simulated_notice_log: str | None = None


class AdminAlertActionSuccessResponse(BaseModel):
    """Standard success envelope for alert action responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminAlertActionData
