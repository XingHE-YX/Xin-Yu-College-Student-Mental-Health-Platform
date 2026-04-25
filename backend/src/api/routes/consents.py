"""Student consent submission routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from src.core.auth import get_current_student
from src.core.database import get_db_session
from src.core.security import AccessTokenService
from src.models.student_user import StudentUser
from src.schemas.consent import (
    ConsentRecordResponse,
    ConsentSubmissionData,
    ConsentSubmissionRequest,
    ConsentSubmissionSuccessResponse,
)
from src.schemas.student_auth import StudentProfileResponse
from src.services.student_consent_service import StudentConsentService

router = APIRouter(tags=["consents"])


def build_request_id() -> str:
    """Return a short opaque request identifier for API envelopes."""
    return uuid4().hex


def build_student_profile(student: StudentUser) -> StudentProfileResponse:
    """Serialize the current student into the shared auth payload shape."""
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
    "/consents",
    response_model=ConsentSubmissionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def submit_consent(
    payload: ConsentSubmissionRequest,
    request: Request,
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConsentSubmissionSuccessResponse:
    """Persist a student consent decision and sync derived auth state."""
    token_service: AccessTokenService = request.app.state.access_token_service
    service = StudentConsentService(session, token_service=token_service)
    result = service.submit_consent(
        student=student,
        payload=payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return ConsentSubmissionSuccessResponse(
        request_id=build_request_id(),
        data=ConsentSubmissionData(
            access_token=result.access_token,
            student=build_student_profile(result.student),
            consent_record=ConsentRecordResponse(
                id=result.consent_record.id,
                consent_type=result.consent_record.consent_type,
                consent_version=result.consent_record.consent_version,
                granted=result.consent_record.granted,
                granted_at=result.consent_record.granted_at,
            ),
        ),
    )
