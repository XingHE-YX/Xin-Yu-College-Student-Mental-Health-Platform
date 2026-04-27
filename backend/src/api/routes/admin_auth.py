"""Administrator authentication routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.core.auth import get_current_admin
from src.core.database import get_db_session
from src.core.security import AccessTokenService
from src.models.admin_user import AdminUser
from src.schemas.admin_auth import (
    AdminLoginRequest,
    AdminProfileData,
    AdminProfileResponse,
    AdminProfileSuccessResponse,
    AdminSessionData,
    AdminSessionSuccessResponse,
)
from src.services.admin_auth_service import (
    AdminAccountInactiveError,
    AdminAuthService,
    InvalidAdminCredentialsError,
)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


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


def build_admin_auth_service(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminAuthService:
    """Build a request-scoped administrator auth service."""
    token_service: AccessTokenService = request.app.state.access_token_service
    return AdminAuthService(session, token_service=token_service)


def build_admin_profile_response(admin: AdminUser) -> AdminProfileResponse:
    """Serialize the persisted administrator into the auth response shape."""
    return AdminProfileResponse(
        id=admin.id,
        username=admin.username,
        display_name=admin.display_name,
        role_code=admin.role_code,
        is_active=admin.is_active,
        last_login_at=admin.last_login_at,
    )


@router.post(
    "/login",
    response_model=AdminSessionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    auth_service: Annotated[AdminAuthService, Depends(build_admin_auth_service)],
) -> AdminSessionSuccessResponse | JSONResponse:
    """Authenticate one administrator and issue a JWT session."""
    try:
        result = auth_service.login(
            username=payload.username,
            password=payload.password,
            ip_address=request.client.host if request.client is not None else None,
        )
    except InvalidAdminCredentialsError as exc:
        return build_error_response(
            http_status=status.HTTP_401_UNAUTHORIZED,
            code="ADMIN_AUTH_INVALID_CREDENTIALS",
            message=str(exc),
        )
    except AdminAccountInactiveError as exc:
        return build_error_response(
            http_status=status.HTTP_403_FORBIDDEN,
            code="ADMIN_ACCOUNT_INACTIVE",
            message=str(exc),
        )

    return AdminSessionSuccessResponse(
        request_id=build_request_id(),
        data=AdminSessionData(
            access_token=result.access_token,
            admin=build_admin_profile_response(result.admin),
        ),
    )


@router.get(
    "/me",
    response_model=AdminProfileSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_current_admin_profile(
    admin: Annotated[AdminUser, Depends(get_current_admin)],
) -> AdminProfileSuccessResponse:
    """Return the authenticated administrator profile."""
    return AdminProfileSuccessResponse(
        request_id=build_request_id(),
        data=AdminProfileData(admin=build_admin_profile_response(admin)),
    )
