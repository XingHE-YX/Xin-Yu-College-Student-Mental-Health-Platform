"""Public runtime feature routes used by frontend clients during demo mode."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status

from src.core.settings import Settings
from src.schemas.runtime_features import (
    RuntimeFeaturesResponse,
    RuntimeFeaturesSuccessResponse,
)

router = APIRouter(prefix="/runtime", tags=["runtime"])


def build_request_id() -> str:
    """Return a short opaque request identifier for API envelopes."""
    return uuid4().hex


def get_runtime_settings(request: Request) -> Settings:
    """Return the cached application settings attached to the FastAPI app."""
    return request.app.state.settings


@router.get(
    "/features",
    response_model=RuntimeFeaturesSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_runtime_features(
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> RuntimeFeaturesSuccessResponse:
    """Expose the public runtime flags needed by student and demo entry flows."""
    return RuntimeFeaturesSuccessResponse(
        request_id=build_request_id(),
        data=RuntimeFeaturesResponse(
            enable_demo_login=settings.enable_demo_login,
            enable_mock_ai=settings.enable_mock_ai,
            show_seeded_cases=settings.show_seeded_cases,
            demo_mode_enabled=any(
                (
                    settings.enable_demo_login,
                    settings.enable_mock_ai,
                    settings.show_seeded_cases,
                )
            ),
        ),
    )
