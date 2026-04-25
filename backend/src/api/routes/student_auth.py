"""Student authentication routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.core.security import AccessTokenService
from src.core.settings import Settings
from src.models.student_user import StudentUser
from src.schemas.student_auth import (
    StudentProfileResponse,
    StudentSessionData,
    StudentSessionSuccessResponse,
    StudentWechatLoginRequest,
)
from src.services.student_auth_service import (
    DemoLoginDisabledError,
    InvalidPhoneTicketError,
    StudentAuthService,
    StudentLoginConflictError,
)
from src.services.wechat_session_service import (
    WeChatSessionExchangeError,
    WeChatSessionService,
)

router = APIRouter(prefix="/auth/student", tags=["student-auth"])


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


def build_student_auth_service(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> StudentAuthService:
    """Build a request-scoped student auth service."""
    settings: Settings = request.app.state.settings
    token_service: AccessTokenService = request.app.state.access_token_service
    wechat_session_service: WeChatSessionService = request.app.state.wechat_session_service
    return StudentAuthService(
        session,
        settings=settings,
        token_service=token_service,
        wechat_session_service=wechat_session_service,
    )


def build_student_profile_response(student: StudentUser) -> StudentProfileResponse:
    """Serialize the persisted student into the login response shape."""
    return StudentProfileResponse(
        id=student.id,
        display_nickname=student.display_nickname,
        display_avatar_seed=student.display_avatar_seed,
        college_name=student.college_name,
        class_name=student.class_name,
        consent_status=student.consent_status,
        risk_status=student.risk_status,
        is_demo=student.is_demo,
    )


@router.post(
    "/wechat-login",
    response_model=StudentSessionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def wechat_login(
    payload: StudentWechatLoginRequest,
    auth_service: Annotated[StudentAuthService, Depends(build_student_auth_service)],
) -> StudentSessionSuccessResponse | JSONResponse:
    """Create or refresh a student session via WeChat login."""
    try:
        result = auth_service.login_with_wechat(payload)
    except InvalidPhoneTicketError as exc:
        return build_error_response(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message=str(exc),
        )
    except StudentLoginConflictError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="STUDENT_AUTH_CONFLICT",
            message=str(exc),
        )
    except WeChatSessionExchangeError as exc:
        return build_error_response(
            http_status=status.HTTP_502_BAD_GATEWAY,
            code="WECHAT_AUTH_FAILED",
            message=str(exc),
        )

    return StudentSessionSuccessResponse(
        request_id=build_request_id(),
        data=StudentSessionData(
            access_token=result.access_token,
            student=build_student_profile_response(result.student),
        ),
    )


@router.post(
    "/demo-login",
    response_model=StudentSessionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def demo_login(
    auth_service: Annotated[StudentAuthService, Depends(build_student_auth_service)],
) -> StudentSessionSuccessResponse | JSONResponse:
    """Create or refresh the fixed demo student account."""
    try:
        result = auth_service.login_demo_student()
    except DemoLoginDisabledError as exc:
        return build_error_response(
            http_status=status.HTTP_403_FORBIDDEN,
            code="DEMO_LOGIN_DISABLED",
            message=str(exc),
        )

    return StudentSessionSuccessResponse(
        request_id=build_request_id(),
        data=StudentSessionData(
            access_token=result.access_token,
            student=build_student_profile_response(result.student),
        ),
    )
