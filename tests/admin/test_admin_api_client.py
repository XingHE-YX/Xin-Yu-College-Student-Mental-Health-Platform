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


def test_get_analytics_trends_uses_trends_endpoint(monkeypatch) -> None:
    """The admin API client should call the analytics trends route with bearer auth."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        return {
            "data": {
                "analytics": {
                    "generated_at": "2026-04-29T10:30:00",
                    "risk_distribution": {"total_students": 4, "items": []},
                    "daily_trends": {
                        "window_days": 7,
                        "start_date": "2026-04-23",
                        "end_date": "2026-04-29",
                        "items": [],
                    },
                    "alert_processing": {
                        "total_alert_case_count": 5,
                        "items": [],
                    },
                }
            }
        }

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    analytics = client.get_analytics_trends(access_token="jwt-token")

    assert captured == {
        "method": "GET",
        "path": "/admin/analytics/trends",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": None,
    }
    assert analytics["risk_distribution"]["total_students"] == 4
    assert analytics["alert_processing"]["total_alert_case_count"] == 5


def test_list_alerts_passes_queue_status_params(monkeypatch) -> None:
    """Queue-list requests should forward the selected workflow status as query params."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None, params=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        captured["params"] = params
        return {"data": {"items": [], "status_counts": [], "applied_queue_status": "pending_review"}}

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    queue_payload = client.list_alerts(
        access_token="jwt-token",
        queue_status="pending_review",
    )

    assert captured == {
        "method": "GET",
        "path": "/admin/alerts",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": None,
        "params": {"queue_status": "pending_review"},
    }
    assert queue_payload["applied_queue_status"] == "pending_review"


def test_reveal_alert_content_calls_explicit_reveal_endpoint(monkeypatch) -> None:
    """Raw-content reveal requests should use the dedicated audited endpoint."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None, params=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        captured["params"] = params
        return {"data": {"alert_id": 9, "source_type": "treehole", "full_content": "raw"}}

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    reveal_payload = client.reveal_alert_content(
        access_token="jwt-token",
        alert_id=9,
    )

    assert captured == {
        "method": "POST",
        "path": "/admin/alerts/9/reveal-content",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": None,
        "params": None,
    }
    assert reveal_payload["full_content"] == "raw"


def test_list_posts_passes_publish_status_params(monkeypatch) -> None:
    """Post-list requests should forward the selected publication status."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None, params=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        captured["params"] = params
        return {"data": {"items": [], "status_counts": [], "applied_publish_status": "published"}}

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    post_payload = client.list_posts(
        access_token="jwt-token",
        publish_status="published",
    )

    assert captured == {
        "method": "GET",
        "path": "/admin/posts",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": None,
        "params": {"publish_status": "published"},
    }
    assert post_payload["applied_publish_status"] == "published"


def test_update_post_visibility_calls_patch_endpoint(monkeypatch) -> None:
    """Visibility updates should use the dedicated admin post patch endpoint."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None, params=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        captured["params"] = params
        return {
            "data": {
                "post_id": 7,
                "publish_status": "hidden_by_admin",
                "allow_publication": False,
                "action": "hide",
            }
        }

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    payload = client.update_post_visibility(
        access_token="jwt-token",
        post_id=7,
        action="hide",
    )

    assert captured == {
        "method": "PATCH",
        "path": "/admin/posts/7/visibility",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": {"action": "hide"},
        "params": None,
    }
    assert payload["publish_status"] == "hidden_by_admin"


def test_list_users_passes_risk_status_params(monkeypatch) -> None:
    """User-directory requests should forward the selected risk-status filter."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None, params=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        captured["params"] = params
        return {"data": {"items": [], "status_counts": [], "applied_risk_status": "high"}}

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    payload = client.list_users(
        access_token="jwt-token",
        risk_status="high",
    )

    assert captured == {
        "method": "GET",
        "path": "/admin/users",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": None,
        "params": {"risk_status": "high"},
    }
    assert payload["applied_risk_status"] == "high"


def test_reveal_user_phone_calls_explicit_reveal_endpoint(monkeypatch) -> None:
    """Full-phone reveal requests should use the dedicated audited endpoint."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None, params=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        captured["params"] = params
        return {"data": {"student_id": 4, "full_phone": "+8613812345678"}}

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    payload = client.reveal_user_phone(
        access_token="jwt-token",
        student_id=4,
    )

    assert captured == {
        "method": "POST",
        "path": "/admin/users/4/reveal-phone",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": None,
        "params": None,
    }
    assert payload["full_phone"] == "+8613812345678"


def test_list_audit_logs_passes_filter_params(monkeypatch) -> None:
    """Audit-log requests should forward actor, action, target, and date filters."""
    captured: dict[str, object] = {}

    def fake_request(self, method, path, *, headers=None, json=None, params=None):
        captured["method"] = method
        captured["path"] = path
        captured["headers"] = headers
        captured["json"] = json
        captured["params"] = params
        return {"data": {"records": [], "filtered_count": 0}}

    monkeypatch.setattr(AdminApiClient, "_request", fake_request)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    client.list_audit_logs(
        access_token="jwt-token",
        actor_type="admin",
        actor_id=1,
        action_code="ADMIN_REVEAL_STUDENT_PHONE",
        target_type="student_user",
        date_from="2026-04-28",
        date_to="2026-04-28",
    )

    assert captured == {
        "method": "GET",
        "path": "/admin/audit-logs",
        "headers": {"Authorization": "Bearer jwt-token"},
        "json": None,
        "params": {
            "actor_type": "admin",
            "actor_id": "1",
            "action_code": "ADMIN_REVEAL_STUDENT_PHONE",
            "target_type": "student_user",
            "date_from": "2026-04-28",
            "date_to": "2026-04-28",
        },
    }


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

        def request(self, method, url, *, headers=None, json=None, params=None):
            return DummyResponse()

    monkeypatch.setattr(auth_module.httpx, "Client", DummyClient)

    client = AdminApiClient(api_base_url="http://127.0.0.1:8000/api/v1")
    with pytest.raises(AdminApiRequestError) as exc_info:
        client.get_current_admin(access_token="jwt-token")

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "ADMIN_ACCOUNT_INACTIVE"
    assert exc_info.value.message == "admin account is inactive"
