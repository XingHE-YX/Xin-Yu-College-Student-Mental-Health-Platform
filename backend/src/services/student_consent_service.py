"""Student consent submission service."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.constants.account_enums import ConsentStatus, ConsentType
from src.core.security import AccessTokenService
from src.models.base import utc_now
from src.models.consent_record import ConsentRecord
from src.models.student_user import StudentUser
from src.repositories.consent_record_repository import ConsentRecordRepository
from src.repositories.student_user_repository import StudentUserRepository
from src.schemas.consent import ConsentSubmissionRequest


@dataclass(frozen=True, slots=True)
class StudentConsentResult:
    """A successful consent submission outcome."""

    access_token: str
    student: StudentUser
    consent_record: ConsentRecord


class StudentConsentService:
    """Persist consent decisions and sync current student authorization state."""

    def __init__(
        self,
        session: Session,
        *,
        token_service: AccessTokenService,
    ) -> None:
        self.session = session
        self.token_service = token_service
        self.student_repository = StudentUserRepository(session)
        self.consent_repository = ConsentRecordRepository(session)

    def submit_consent(
        self,
        *,
        student: StudentUser,
        payload: ConsentSubmissionRequest,
        ip_address: str | None,
        user_agent: str | None,
    ) -> StudentConsentResult:
        """Append a consent record and refresh derived student consent status."""
        consent_record = self.consent_repository.create_record(
            student_id=student.id,
            consent_type=payload.consent_type,
            consent_version=payload.consent_version,
            granted=payload.granted,
            granted_at=utc_now(),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if payload.consent_type is ConsentType.CRISIS_INTERVENTION_AUTHORIZATION:
            self.student_repository.update_consent_status(
                student,
                consent_status=(
                    ConsentStatus.GRANTED
                    if payload.granted
                    else ConsentStatus.DECLINED
                ),
            )

        self.session.commit()
        self.session.refresh(student)
        self.session.refresh(consent_record)
        access_token = self.token_service.issue_student_access_token(student)
        return StudentConsentResult(
            access_token=access_token,
            student=student,
            consent_record=consent_record,
        )
