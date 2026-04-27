"""Request and response schemas for administrator authentication APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.constants.account_enums import AdminRoleCode


class AdminLoginRequest(BaseModel):
    """Payload for `POST /api/v1/admin/auth/login`."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)


class AdminProfileResponse(BaseModel):
    """Authenticated administrator profile returned by auth APIs."""

    model_config = ConfigDict(extra="forbid")

    id: int
    username: str
    display_name: str
    role_code: AdminRoleCode
    is_active: bool
    last_login_at: datetime | None


class AdminSessionData(BaseModel):
    """Payload returned after a successful administrator login."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    admin: AdminProfileResponse


class AdminSessionSuccessResponse(BaseModel):
    """Standard success envelope for administrator login responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminSessionData


class AdminProfileData(BaseModel):
    """Payload returned by `GET /api/v1/admin/auth/me`."""

    model_config = ConfigDict(extra="forbid")

    admin: AdminProfileResponse


class AdminProfileSuccessResponse(BaseModel):
    """Standard success envelope for current-admin responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminProfileData
