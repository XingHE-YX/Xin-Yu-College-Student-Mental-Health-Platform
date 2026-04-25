"""Request and response schemas for consent submission APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.constants.account_enums import ConsentType
from src.schemas.student_auth import StudentProfileResponse


class ConsentSubmissionRequest(BaseModel):
    """Payload for `POST /api/v1/consents`."""

    model_config = ConfigDict(extra="forbid")

    consent_type: ConsentType
    consent_version: str = Field(min_length=1, max_length=16)
    granted: bool


class ConsentRecordResponse(BaseModel):
    """Serializable consent-record payload returned after submission."""

    model_config = ConfigDict(extra="forbid")

    id: int
    consent_type: ConsentType
    consent_version: str
    granted: bool
    granted_at: datetime


class ConsentSubmissionData(BaseModel):
    """Business payload returned by the consent submission endpoint."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    student: StudentProfileResponse
    consent_record: ConsentRecordResponse


class ConsentSubmissionSuccessResponse(BaseModel):
    """Standard success envelope for consent submission."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: ConsentSubmissionData
