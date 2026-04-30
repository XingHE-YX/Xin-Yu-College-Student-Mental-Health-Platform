"""Tests for the public runtime feature flags endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.core.settings import Settings
from src.main import create_app
from src.models import Base


def build_settings(
    database_file: Path,
    *,
    enable_demo_login: bool,
    enable_mock_ai: bool,
    show_seeded_cases: bool,
) -> Settings:
    """Create runtime settings for isolated runtime-feature API tests."""
    return Settings(
        APP_NAME="心语运行时特性测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=enable_demo_login,
        ENABLE_MOCK_AI=enable_mock_ai,
        SHOW_SEEDED_CASES=show_seeded_cases,
    )


def create_runtime_feature_test_app(
    database_file: Path,
    *,
    enable_demo_login: bool,
    enable_mock_ai: bool,
    show_seeded_cases: bool,
):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(
        build_settings(
            database_file,
            enable_demo_login=enable_demo_login,
            enable_mock_ai=enable_mock_ai,
            show_seeded_cases=show_seeded_cases,
        )
    )
    Base.metadata.create_all(app.state.db_engine)
    return app


def test_runtime_features_endpoint_returns_public_demo_flags(tmp_path: Path) -> None:
    """The frontend runtime endpoint should expose only the public feature toggles."""
    app = create_runtime_feature_test_app(
        tmp_path / "runtime-features.db",
        enable_demo_login=True,
        enable_mock_ai=True,
        show_seeded_cases=False,
    )
    client = TestClient(app)

    response = client.get("/api/v1/runtime/features")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["message"] == "success"
    assert payload["data"] == {
        "enable_demo_login": True,
        "enable_mock_ai": True,
        "show_seeded_cases": False,
        "demo_mode_enabled": True,
    }
