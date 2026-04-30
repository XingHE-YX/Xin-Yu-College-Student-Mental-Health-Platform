"""Administrator user-directory routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.constants.account_enums import StudentRiskStatus
from src.core.auth import get_current_admin
from src.core.database import get_db_session
from src.models.admin_user import AdminUser
from src.schemas.admin_user_directory import (
    AdminStudentDetailData,
    AdminStudentDetailSuccessResponse,
    AdminStudentListData,
    AdminStudentListItemResponse,
    AdminStudentListSuccessResponse,
    AdminStudentRevealPhoneData,
    AdminStudentRevealPhoneSuccessResponse,
    AdminStudentRiskStatusCountResponse,
)
from src.services.admin_user_directory_service import (
    AdminStudentNotFoundError,
    AdminUserDirectoryService,
)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def build_request_id() -> str:
    """Return a short opaque request identifier for API envelopes."""
    return uuid4().hex


def build_error_response(
    *,
    http_status: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Return a business-style error envelope."""
    return JSONResponse(
        status_code=http_status,
        content={
            "code": code,
            "message": message,
            "request_id": build_request_id(),
        },
    )


@router.get(
    "",
    response_model=AdminStudentListSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def list_admin_users(
    request: Request,
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    risk_status: StudentRiskStatus | None = None,
) -> AdminStudentListSuccessResponse:
    """Return the filtered A06 masked student directory."""
    snapshot = AdminUserDirectoryService(
        session,
        show_seeded_cases=request.app.state.settings.show_seeded_cases,
    ).list_students(risk_status=risk_status)
    return AdminStudentListSuccessResponse(
        request_id=build_request_id(),
        data=AdminStudentListData(
            applied_risk_status=snapshot.applied_risk_status,
            status_counts=[
                AdminStudentRiskStatusCountResponse(
                    risk_status=item.risk_status,
                    count=item.count,
                )
                for item in snapshot.status_counts
            ],
            items=[
                AdminStudentListItemResponse(
                    student_id=item.student_id,
                    student_label=item.student_label,
                    masked_phone=item.masked_phone,
                    college_name=item.college_name,
                    class_name=item.class_name,
                    risk_status=item.risk_status,
                    consent_status=item.consent_status,
                    active_focus_count=item.active_focus_count,
                    open_alert_count=item.open_alert_count,
                    last_login_at=item.last_login_at,
                    updated_at=item.updated_at,
                )
                for item in snapshot.items
            ],
        ),
    )


@router.get(
    "/{student_id}",
    response_model=AdminStudentDetailSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_admin_user_detail(
    student_id: int,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminStudentDetailSuccessResponse | JSONResponse:
    """Return one masked A06 student detail payload and audit the explicit view."""
    try:
        student_payload = AdminUserDirectoryService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).get_student_detail(
            student_id=student_id,
            admin_user_id=admin.id,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AdminStudentNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="STUDENT_NOT_FOUND",
            message=str(exc),
        )

    return AdminStudentDetailSuccessResponse(
        request_id=build_request_id(),
        data=AdminStudentDetailData(student=student_payload),
    )


@router.post(
    "/{student_id}/reveal-phone",
    response_model=AdminStudentRevealPhoneSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def reveal_admin_user_phone(
    student_id: int,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminStudentRevealPhoneSuccessResponse | JSONResponse:
    """Reveal one student's full phone number after explicit admin confirmation."""
    try:
        payload = AdminUserDirectoryService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).reveal_student_phone(
            student_id=student_id,
            admin_user_id=admin.id,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AdminStudentNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="STUDENT_NOT_FOUND",
            message=str(exc),
        )

    return AdminStudentRevealPhoneSuccessResponse(
        request_id=build_request_id(),
        data=AdminStudentRevealPhoneData(**payload),
    )
