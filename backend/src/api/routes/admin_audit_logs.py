"""Administrator audit-log routes."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.constants.workflow_enums import AuditActorType
from src.core.auth import get_current_admin
from src.core.database import get_db_session
from src.models.admin_user import AdminUser
from src.schemas.admin_audit_log import (
    AdminAuditLogAppliedFiltersResponse,
    AdminAuditLogListData,
    AdminAuditLogListSuccessResponse,
    AdminAuditLogRecordResponse,
    AuditActorOptionResponse,
)
from src.services.admin_audit_log_service import AdminAuditLogService

router = APIRouter(prefix="/admin/audit-logs", tags=["admin-audit-logs"])


def build_request_id() -> str:
    """Return a short opaque request identifier for API envelopes."""
    return uuid4().hex


@router.get(
    "",
    response_model=AdminAuditLogListSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def list_admin_audit_logs(
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    actor_type: AuditActorType | None = None,
    actor_id: int | None = None,
    action_code: str | None = None,
    target_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AdminAuditLogListSuccessResponse:
    """Return the filtered A07 audit-log payload."""
    snapshot = AdminAuditLogService(session).list_audit_logs(
        actor_type=actor_type,
        actor_id=actor_id,
        action_code=action_code,
        target_type=target_type,
        date_from=date_from,
        date_to=date_to,
    )
    return AdminAuditLogListSuccessResponse(
        request_id=build_request_id(),
        data=AdminAuditLogListData(
            filtered_count=snapshot.filtered_count,
            applied_filters=AdminAuditLogAppliedFiltersResponse(
                actor_type=actor_type,
                actor_id=actor_id,
                action_code=action_code,
                target_type=target_type,
                date_from=date_from,
                date_to=date_to,
            ),
            actor_options=[
                AuditActorOptionResponse(
                    actor_type=item.actor_type,
                    actor_id=item.actor_id,
                    label=item.label,
                )
                for item in snapshot.actor_options
            ],
            action_code_options=snapshot.action_code_options,
            target_type_options=snapshot.target_type_options,
            records=[
                AdminAuditLogRecordResponse(**record)
                for record in snapshot.records
            ],
        ),
    )
