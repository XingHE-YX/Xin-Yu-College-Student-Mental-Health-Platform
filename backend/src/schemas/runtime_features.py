"""Schemas for public runtime feature flags exposed to frontend clients."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RuntimeFeaturesResponse(BaseModel):
    """Public runtime flags that influence demo-mode behavior."""

    model_config = ConfigDict(extra="forbid")

    enable_demo_login: bool
    enable_mock_ai: bool
    show_seeded_cases: bool
    demo_mode_enabled: bool = Field(
        description="Whether any explicit demo-support switch is currently enabled."
    )


class RuntimeFeaturesSuccessResponse(BaseModel):
    """Standard success envelope for runtime feature reads."""

    model_config = ConfigDict(extra="forbid")

    code: str = "OK"
    message: str = "success"
    request_id: str
    data: RuntimeFeaturesResponse
