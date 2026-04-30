"""Administrator alert queue and detail routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.constants.workflow_enums import AlertQueueStatus
from src.core.auth import get_current_admin
from src.core.database import get_db_session
from src.models.admin_user import AdminUser
from src.schemas.admin_alert import (
    AdminAlertActionData,
    AdminAlertActionSuccessResponse,
    AdminAlertAddNoteRequest,
    AdminAlertCloseRequest,
    AdminAlertConfirmRequest,
    AdminAlertDetailData,
    AdminAlertDetailSuccessResponse,
    AdminAlertDismissRequest,
    AdminAlertListData,
    AdminAlertListItemResponse,
    AdminAlertListSuccessResponse,
    AdminAlertQueueStatusCountResponse,
    AdminAlertRevealContentData,
    AdminAlertRevealContentSuccessResponse,
)
from src.services.admin_alert_service import (
    AdminAlertService,
    AlertCaseNotFoundError,
    AlertSourceContentUnavailableError,
)
from src.services.alert_review_service import (
    AlertCaseNotFoundError as AlertReviewCaseNotFoundError,
)
from src.services.alert_review_service import (
    AlertReviewService,
    AlertReviewServiceError,
    InvalidAlertCaseTransitionError,
)

router = APIRouter(prefix="/admin/alerts", tags=["admin-alerts"])


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
    response_model=AdminAlertListSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def list_admin_alerts(
    request: Request,
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    queue_status: AlertQueueStatus | None = None,
) -> AdminAlertListSuccessResponse:
    """Return the filtered A03 alert queue for the authenticated administrator."""
    queue_snapshot = AdminAlertService(
        session,
        show_seeded_cases=request.app.state.settings.show_seeded_cases,
    ).list_alert_queue(
        queue_status=queue_status
    )
    return AdminAlertListSuccessResponse(
        request_id=build_request_id(),
        data=AdminAlertListData(
            applied_queue_status=queue_snapshot.applied_queue_status,
            status_counts=[
                AdminAlertQueueStatusCountResponse(
                    queue_status=item.queue_status,
                    count=item.count,
                )
                for item in queue_snapshot.status_counts
            ],
            items=[
                AdminAlertListItemResponse(
                    alert_id=item.alert_id,
                    created_at=item.created_at,
                    queue_status=item.queue_status,
                    review_priority=item.review_priority,
                    case_level=item.case_level,
                    source_type=item.source_type,
                    source_label=item.source_label,
                    source_preview=item.source_preview,
                    student_label=item.student_label,
                    masked_phone=item.masked_phone,
                    college_name=item.college_name,
                    class_name=item.class_name,
                    risk_status=item.risk_status,
                    reviewer_display_name=item.reviewer_display_name,
                    reviewed_at=item.reviewed_at,
                )
                for item in queue_snapshot.items
            ],
        ),
    )


@router.get(
    "/{alert_id}",
    response_model=AdminAlertDetailSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_admin_alert_detail(
    alert_id: int,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminAlertDetailSuccessResponse | JSONResponse:
    """Return one A04 alert detail payload and audit the sensitive view."""
    try:
        alert_payload = AdminAlertService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).get_alert_detail(
            alert_case_id=alert_id,
            admin_user_id=admin.id,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AlertCaseNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="ALERT_CASE_NOT_FOUND",
            message=str(exc),
        )

    return AdminAlertDetailSuccessResponse(
        request_id=build_request_id(),
        data=AdminAlertDetailData(alert=alert_payload),
    )


@router.post(
    "/{alert_id}/reveal-content",
    response_model=AdminAlertRevealContentSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def reveal_admin_alert_content(
    alert_id: int,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminAlertRevealContentSuccessResponse | JSONResponse:
    """Reveal one treehole alert's raw content after explicit admin confirmation."""
    try:
        content_payload = AdminAlertService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).reveal_treehole_content(
            alert_case_id=alert_id,
            admin_user_id=admin.id,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AlertCaseNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="ALERT_CASE_NOT_FOUND",
            message=str(exc),
        )
    except AlertSourceContentUnavailableError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="ALERT_SOURCE_CONTENT_UNAVAILABLE",
            message=str(exc),
        )

    return AdminAlertRevealContentSuccessResponse(
        request_id=build_request_id(),
        data=AdminAlertRevealContentData(**content_payload),
    )


@router.post(
    "/{alert_id}/confirm",
    response_model=AdminAlertActionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def confirm_admin_alert(
    alert_id: int,
    payload: AdminAlertConfirmRequest,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminAlertActionSuccessResponse | JSONResponse:
    """Confirm one pending alert case as high risk."""
    try:
        result = AlertReviewService(session).confirm_high_risk(
            alert_case_id=alert_id,
            admin_user_id=admin.id,
            review_note=payload.review_note,
            intervention_note=payload.intervention_note,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AlertReviewCaseNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="ALERT_CASE_NOT_FOUND",
            message=str(exc),
        )
    except InvalidAlertCaseTransitionError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="ALERT_CASE_TRANSITION_CONFLICT",
            message=str(exc),
        )
    except AlertReviewServiceError as exc:
        return build_error_response(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="ALERT_REVIEW_INVALID_REQUEST",
            message=str(exc),
        )

    return build_action_success_response(result.alert_case)


@router.post(
    "/{alert_id}/dismiss",
    response_model=AdminAlertActionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def dismiss_admin_alert(
    alert_id: int,
    payload: AdminAlertDismissRequest,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminAlertActionSuccessResponse | JSONResponse:
    """Dismiss one pending alert case as a false positive."""
    try:
        result = AlertReviewService(session).dismiss_false_positive(
            alert_case_id=alert_id,
            admin_user_id=admin.id,
            review_note=payload.review_note,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AlertReviewCaseNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="ALERT_CASE_NOT_FOUND",
            message=str(exc),
        )
    except InvalidAlertCaseTransitionError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="ALERT_CASE_TRANSITION_CONFLICT",
            message=str(exc),
        )
    except AlertReviewServiceError as exc:
        return build_error_response(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="ALERT_REVIEW_INVALID_REQUEST",
            message=str(exc),
        )

    return build_action_success_response(result.alert_case)


@router.post(
    "/{alert_id}/close",
    response_model=AdminAlertActionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def close_admin_alert(
    alert_id: int,
    payload: AdminAlertCloseRequest,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminAlertActionSuccessResponse | JSONResponse:
    """Close one reviewed alert case."""
    try:
        result = AlertReviewService(session).close_case(
            alert_case_id=alert_id,
            admin_user_id=admin.id,
            action_note=payload.action_note,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AlertReviewCaseNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="ALERT_CASE_NOT_FOUND",
            message=str(exc),
        )
    except InvalidAlertCaseTransitionError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="ALERT_CASE_TRANSITION_CONFLICT",
            message=str(exc),
        )
    except AlertReviewServiceError as exc:
        return build_error_response(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="ALERT_REVIEW_INVALID_REQUEST",
            message=str(exc),
        )

    return build_action_success_response(result.alert_case)


@router.post(
    "/{alert_id}/notes",
    response_model=AdminAlertActionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def add_admin_alert_note(
    alert_id: int,
    payload: AdminAlertAddNoteRequest,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminAlertActionSuccessResponse | JSONResponse:
    """Append one intervention note to the current alert case timeline."""
    try:
        result = AlertReviewService(session).add_intervention_note(
            alert_case_id=alert_id,
            admin_user_id=admin.id,
            action_note=payload.action_note,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AlertReviewCaseNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="ALERT_CASE_NOT_FOUND",
            message=str(exc),
        )
    except InvalidAlertCaseTransitionError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="ALERT_CASE_TRANSITION_CONFLICT",
            message=str(exc),
        )
    except AlertReviewServiceError as exc:
        return build_error_response(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="ALERT_REVIEW_INVALID_REQUEST",
            message=str(exc),
        )

    return build_action_success_response(result.alert_case)


def build_action_success_response(alert_case) -> AdminAlertActionSuccessResponse:
    """Serialize one alert-review action result into the standard success envelope."""
    return AdminAlertActionSuccessResponse(
        request_id=build_request_id(),
        data=AdminAlertActionData(
            alert_id=alert_case.id,
            queue_status=alert_case.queue_status,
            simulated_notice_log=alert_case.simulated_notice_log,
        ),
    )
