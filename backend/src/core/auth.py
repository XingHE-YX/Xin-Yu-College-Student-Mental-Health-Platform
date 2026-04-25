"""Authentication dependencies for student-protected API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.core.security import (
    AccessTokenService,
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
)
from src.models.student_user import StudentUser
from src.repositories.student_user_repository import StudentUserRepository

student_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_student(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(student_bearer_scheme),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> StudentUser:
    """Resolve the authenticated student from the bearer access token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="student access token is required",
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="student access token must use the Bearer scheme",
        )

    token_service: AccessTokenService = request.app.state.access_token_service
    try:
        payload = token_service.decode_access_token(
            credentials.credentials,
            expected_role="student",
        )
    except (ExpiredAccessTokenError, InvalidAccessTokenError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    student_id = _extract_student_id(payload)
    repository = StudentUserRepository(session)
    student = repository.get_by_id(student_id)
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="student account no longer exists",
        )
    return student


def _extract_student_id(payload: dict[str, Any]) -> int:
    """Read `student_id` from a verified student token payload."""
    student_id = payload.get("student_id")
    if not isinstance(student_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="student access token payload is invalid",
        )
    return student_id
