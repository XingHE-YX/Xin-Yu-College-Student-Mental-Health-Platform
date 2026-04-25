"""Repository helpers for immutable student consent records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from src.constants.account_enums import ConsentType
from src.models.consent_record import ConsentRecord


class ConsentRecordRepository:
    """Persist append-only consent decision rows."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_record(
        self,
        *,
        student_id: int,
        consent_type: ConsentType,
        consent_version: str,
        granted: bool,
        granted_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> ConsentRecord:
        """Insert one immutable consent decision."""
        record = ConsentRecord(
            student_id=student_id,
            consent_type=consent_type,
            consent_version=consent_version,
            granted=granted,
            granted_at=granted_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(record)
        self.session.flush()
        return record
