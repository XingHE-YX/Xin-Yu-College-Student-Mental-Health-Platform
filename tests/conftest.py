"""Shared pytest bootstrap for repository-level test discovery."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

for candidate in (BACKEND_ROOT,):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

os.environ.setdefault("APP_NAME", "心语后端服务")
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("API_V1_PREFIX", "/api/v1")
os.environ.setdefault(
    "DATABASE_URL",
    "mysql+pymysql://xinyu_user:test_password@127.0.0.1:3306/xinyu_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-api-key")
os.environ.setdefault("WECHAT_APP_ID", "test-wechat-app-id")
os.environ.setdefault("WECHAT_APP_SECRET", "test-wechat-app-secret")
os.environ.setdefault("ENABLE_DEMO_LOGIN", "true")
