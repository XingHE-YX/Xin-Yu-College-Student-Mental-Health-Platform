"""Request and response schemas for student authentication."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.constants.account_enums import ConsentStatus, StudentRiskStatus


class StudentWechatLoginRequest(BaseModel):
    """Payload for `POST /auth/student/wechat-login`."""

    model_config = ConfigDict(extra="forbid")

    login_code: str = Field(min_length=1, max_length=256)
    phone_ticket: str = Field(min_length=1, max_length=4096)
    phone_signature: str | None = Field(default=None, max_length=512)
    consent_status: ConsentStatus | None = None


class StudentProfileResponse(BaseModel):
    """Minimal student profile returned after successful login."""

    model_config = ConfigDict(extra="forbid")

    id: int
    display_nickname: str
    display_avatar_seed: str
    college_name: str
    class_name: str
    consent_status: ConsentStatus
    risk_status: StudentRiskStatus
    is_demo: bool


class StudentSessionData(BaseModel):
    """Student access token and profile payload."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    student: StudentProfileResponse


class StudentSessionSuccessResponse(BaseModel):
    """Standard success envelope for login endpoints."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: StudentSessionData
