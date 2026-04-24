"""Smoke tests for the initial FastAPI application skeleton."""

from fastapi.testclient import TestClient

from src.main import app


def test_health_check_returns_200() -> None:
    """The health endpoint should be available after step 2.1 bootstrap."""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_state_contains_runtime_settings() -> None:
    """The application should expose environment-backed settings on app.state."""
    assert app.state.settings.api_v1_prefix == "/api/v1"
    assert app.state.settings.enable_demo_login is True
