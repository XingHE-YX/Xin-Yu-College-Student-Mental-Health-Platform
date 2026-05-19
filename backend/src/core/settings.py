"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized runtime configuration for the backend service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="心语后端服务", validation_alias="APP_NAME")
    app_env: Literal["development", "testing", "staging", "production"] = Field(
        default="development",
        validation_alias="APP_ENV",
    )
    api_v1_prefix: str = Field(default="/api/v1", validation_alias="API_V1_PREFIX")
    database_url: str = Field(validation_alias="DATABASE_URL")
    jwt_secret_key: SecretStr = Field(validation_alias="JWT_SECRET_KEY")
    deepseek_api_key: SecretStr = Field(validation_alias="DEEPSEEK_API_KEY")
    deepseek_model_name: str = Field(
        default="deepseek-v4-flash",
        validation_alias="DEEPSEEK_MODEL_NAME",
    )
    wechat_app_id: str = Field(validation_alias="WECHAT_APP_ID")
    wechat_app_secret: SecretStr = Field(validation_alias="WECHAT_APP_SECRET")
    enable_demo_login: bool = Field(default=False, validation_alias="ENABLE_DEMO_LOGIN")
    enable_mock_ai: bool = Field(default=False, validation_alias="ENABLE_MOCK_AI")
    show_seeded_cases: bool = Field(default=False, validation_alias="SHOW_SEEDED_CASES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache the application settings."""
    return Settings()
