"""Tests for the Streamlit administrator API client helpers."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import admin.services.auth as auth_module  # noqa: E402
from admin.services.auth import AdminApiClient, AdminApiRequestError  # noqa: E402


def test_get_dashboard_summary_uses_summary_endpoint(monkeypatch) -> None:
    """The admin API client should call the dashboard summary route with bearer auth."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        return {
            "data": {
                "summary": {
                    "generated_at": "2026-04-27T09:30:00",
                    "kpis": {"pending_review_count": 2},
                    "stats": {"blocked_post_count": 1},
                }
            }
        }

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    summary = client.get_dashboard_summary(access_token="jwt-token")

    assert captured == {
        "method": "GET",
        "path": "/admin/dashboard/summary",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": None,
    }
    assert summary["generated_at"] == "2026-04-27T09:30:00"
    assert summary["kpis"]["pending_review_count"] == 2


def test_request_uses_detail_payload_for_inactive_admin_errors(monkeypatch) -> None:
    """Auth dependency errors returned as `detail` should still map to a useful code."""

    class DummyResponse:
        status_code = 403

        @staticmethod
        def json():
            return {"detail": "admin account is inactive"}

    class DummyClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, url, *, headers=None, json=None):
            return DummyResponse()

    monkeypatch.setattr(auth_module.httpx, "Client", DummyClient)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    with pytest.raises(AdminApiRequestError) as exc_info:
        client.get_current_admin(access_token="jwt-token")

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "ADMIN_ACCOUNT_INACTIVE"
    assert exc_info.value.message == "admin account is inactive"
