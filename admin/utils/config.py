"""Configuration helpers for the Streamlit admin console."""

from __future__ import annotations

import os

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1"


def get_admin_api_base_url() -> str:
    """Return the backend API base URL used by Streamlit admin requests."""
    return (
        os.getenv("XINYU_ADMIN_API_BASE_URL")
        or os.getenv("ADMIN_API_BASE_URL")
        or DEFAULT_API_BASE_URL
    )
