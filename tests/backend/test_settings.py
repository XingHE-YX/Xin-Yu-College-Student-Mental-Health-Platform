"""Tests for environment-driven application settings."""

from src.core.settings import get_settings


def test_settings_load_from_environment(monkeypatch) -> None:
    """Settings should be sourced from environment variables instead of hardcoded secrets."""
    monkeypatch.setenv("APP_NAME", "心语测试后端")
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("API_V1_PREFIX", "/api/v1")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://demo:secret@localhost:3306/demo_db")
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-test-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setenv("WECHAT_APP_ID", "wx-test-app-id")
    monkeypatch.setenv("WECHAT_APP_SECRET", "wx-test-secret")
    monkeypatch.setenv("ENABLE_DEMO_LOGIN", "false")

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.app_name == "心语测试后端"
    assert settings.app_env == "testing"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url == "mysql+pymysql://demo:secret@localhost:3306/demo_db"
    assert settings.jwt_secret_key.get_secret_value() == "jwt-test-secret"
    assert settings.deepseek_api_key.get_secret_value() == "deepseek-test-key"
    assert settings.wechat_app_id == "wx-test-app-id"
    assert settings.wechat_app_secret.get_secret_value() == "wx-test-secret"
    assert settings.enable_demo_login is False

    get_settings.cache_clear()
