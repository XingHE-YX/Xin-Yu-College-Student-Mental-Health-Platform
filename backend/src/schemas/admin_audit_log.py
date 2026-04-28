"""Request and response schemas for administrator audit-log APIs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.constants.workflow_enums import AuditActorType


class AuditActorOptionResponse(BaseModel):
    """One actor filter option returned to the A07 page."""

    model_config = ConfigDict(extra="forbid")

    actor_type: AuditActorType
    actor_id: int | None
    label: str


class AdminAuditLogRecordResponse(BaseModel):
    """One formatted audit-log row returned by `GET /api/v1/admin/audit-logs`."""

    model_config = ConfigDict(extra="forbid")

    audit_log_id: int
    created_at: datetime
    actor_type: str
    actor_id: int | None
    actor_label: str
    action_code: str
    target_type: str
    target_id: int | None
    target_label: str
    summary_text: str
    metadata_json: dict[str, Any] | None
    ip_address: str | None


class AdminAuditLogAppliedFiltersResponse(BaseModel):
    """Echo of the currently applied A07 audit-log filters."""

    model_config = ConfigDict(extra="forbid")

    actor_type: AuditActorType | None
    actor_id: int | None
    action_code: str | None
    target_type: str | None
    date_from: date | None
    date_to: date | None


class AdminAuditLogListData(BaseModel):
    """Data payload returned by `GET /api/v1/admin/audit-logs`."""

    model_config = ConfigDict(extra="forbid")

    filtered_count: int
    applied_filters: AdminAuditLogAppliedFiltersResponse
    actor_options: list[AuditActorOptionResponse]
    action_code_options: list[str]
    target_type_options: list[str]
    records: list[AdminAuditLogRecordResponse]


class AdminAuditLogListSuccessResponse(BaseModel):
    """Standard success envelope for audit-log list responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminAuditLogListData
