"""Health check routes."""

from fastapi import APIRouter, status

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> dict[str, str]:
    """Return a minimal health payload for liveness checks."""
    return {"status": "ok"}
