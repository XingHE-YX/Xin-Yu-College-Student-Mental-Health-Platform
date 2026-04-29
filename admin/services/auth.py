"""HTTP client helpers for Streamlit admin API access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class AdminApiClientError(RuntimeError):
    """Base error raised when the Streamlit admin client cannot reach the backend."""


class AdminApiRequestError(AdminApiClientError):
    """Raised when the backend returns a business or auth failure response."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AdminSessionPayload:
    """Normalized administrator session payload returned by the backend."""

    access_token: str
    admin: dict[str, Any]


class AdminApiClient:
    """Call administrator-facing endpoints exposed by the FastAPI backend."""

    def __init__(
        self,
        *,
        api_base_url: str,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def login(self, *, username: str, password: str) -> AdminSessionPayload:
        """Authenticate one administrator via the backend login endpoint."""
        payload = self._request(
            "POST",
            "/admin/auth/login",
            json={
                "username": username,
                "password": password,
            },
        )
        data = payload["data"]
        return AdminSessionPayload(
            access_token=data["access_token"],
            admin=data["admin"],
        )

    def get_current_admin(self, *, access_token: str) -> dict[str, Any]:
        """Return the current authenticated administrator profile."""
        payload = self._request(
            "GET",
            "/admin/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]["admin"]

    def get_dashboard_summary(self, *, access_token: str) -> dict[str, Any]:
        """Return the live summary payload for the A02 dashboard."""
        payload = self._request(
            "GET",
            "/admin/dashboard/summary",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]["summary"]

    def get_analytics_trends(self, *, access_token: str) -> dict[str, Any]:
        """Return the live analytics payload used by the admin chart page."""
        payload = self._request(
            "GET",
            "/admin/analytics/trends",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]["analytics"]

    def list_alerts(
        self,
        *,
        access_token: str,
        queue_status: str | None = None,
    ) -> dict[str, Any]:
        """Return the filtered A03 alert queue payload."""
        params = {"queue_status": queue_status} if queue_status else None
        payload = self._request(
            "GET",
            "/admin/alerts",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        return payload["data"]

    def get_alert_detail(self, *, access_token: str, alert_id: int) -> dict[str, Any]:
        """Return the A04 alert detail payload for one selected alert case."""
        payload = self._request(
            "GET",
            f"/admin/alerts/{alert_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]["alert"]

    def reveal_alert_content(
        self,
        *,
        access_token: str,
        alert_id: int,
    ) -> dict[str, Any]:
        """Reveal raw treehole content for one selected alert case."""
        payload = self._request(
            "POST",
            f"/admin/alerts/{alert_id}/reveal-content",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]

    def confirm_alert(
        self,
        *,
        access_token: str,
        alert_id: int,
        review_note: str,
        intervention_note: str,
    ) -> dict[str, Any]:
        """Confirm one pending alert case as high risk."""
        payload = self._request(
            "POST",
            f"/admin/alerts/{alert_id}/confirm",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "review_note": review_note,
                "intervention_note": intervention_note,
            },
        )
        return payload["data"]

    def dismiss_alert(
        self,
        *,
        access_token: str,
        alert_id: int,
        review_note: str,
    ) -> dict[str, Any]:
        """Dismiss one pending alert case as a false positive."""
        payload = self._request(
            "POST",
            f"/admin/alerts/{alert_id}/dismiss",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"review_note": review_note},
        )
        return payload["data"]

    def close_alert(
        self,
        *,
        access_token: str,
        alert_id: int,
        action_note: str,
    ) -> dict[str, Any]:
        """Close one reviewed alert case."""
        payload = self._request(
            "POST",
            f"/admin/alerts/{alert_id}/close",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"action_note": action_note},
        )
        return payload["data"]

    def add_alert_note(
        self,
        *,
        access_token: str,
        alert_id: int,
        action_note: str,
    ) -> dict[str, Any]:
        """Append one intervention note to the selected alert case timeline."""
        payload = self._request(
            "POST",
            f"/admin/alerts/{alert_id}/notes",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"action_note": action_note},
        )
        return payload["data"]

    def list_posts(
        self,
        *,
        access_token: str,
        publish_status: str | None = None,
    ) -> dict[str, Any]:
        """Return the filtered A05 post-management payload."""
        params = {"publish_status": publish_status} if publish_status else None
        payload = self._request(
            "GET",
            "/admin/posts",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        return payload["data"]

    def get_post_detail(self, *, access_token: str, post_id: int) -> dict[str, Any]:
        """Return the A05 post detail payload for one selected treehole post."""
        payload = self._request(
            "GET",
            f"/admin/posts/{post_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]["post"]

    def reveal_post_content(
        self,
        *,
        access_token: str,
        post_id: int,
    ) -> dict[str, Any]:
        """Reveal raw treehole content for one selected managed post."""
        payload = self._request(
            "POST",
            f"/admin/posts/{post_id}/reveal-content",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]

    def update_post_visibility(
        self,
        *,
        access_token: str,
        post_id: int,
        action: str,
    ) -> dict[str, Any]:
        """Apply one audited admin visibility action to the selected post."""
        payload = self._request(
            "PATCH",
            f"/admin/posts/{post_id}/visibility",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"action": action},
        )
        return payload["data"]

    def list_users(
        self,
        *,
        access_token: str,
        risk_status: str | None = None,
    ) -> dict[str, Any]:
        """Return the filtered A06 user-directory payload."""
        params = {"risk_status": risk_status} if risk_status else None
        payload = self._request(
            "GET",
            "/admin/users",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        return payload["data"]

    def get_user_detail(
        self,
        *,
        access_token: str,
        student_id: int,
    ) -> dict[str, Any]:
        """Return the A06 user-detail payload for one selected student."""
        payload = self._request(
            "GET",
            f"/admin/users/{student_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]["student"]

    def reveal_user_phone(
        self,
        *,
        access_token: str,
        student_id: int,
    ) -> dict[str, Any]:
        """Reveal the full phone number for one selected student."""
        payload = self._request(
            "POST",
            f"/admin/users/{student_id}/reveal-phone",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return payload["data"]

    def list_audit_logs(
        self,
        *,
        access_token: str,
        actor_type: str | None = None,
        actor_id: int | None = None,
        action_code: str | None = None,
        target_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """Return the filtered A07 audit-log payload."""
        params: dict[str, str] = {}
        if actor_type:
            params["actor_type"] = actor_type
        if actor_id is not None:
            params["actor_id"] = str(actor_id)
        if action_code:
            params["action_code"] = action_code
        if target_type:
            params["target_type"] = target_type
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        payload = self._request(
            "GET",
            "/admin/audit-logs",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params or None,
        )
        return payload["data"]

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Perform one backend request and normalize error handling."""
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(
                    method,
                    f"{self.api_base_url}{path}",
                    headers=headers,
                    json=json,
                    params=params,
                )
        except httpx.HTTPError as exc:  # pragma: no cover
            raise AdminApiClientError(f"无法连接后台服务：{exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover
            raise AdminApiClientError("后台返回了无法解析的响应。") from exc

        if response.status_code >= 400:
            detail = payload.get("detail")
            code = payload.get("code")
            message = payload.get("message")
            if not isinstance(code, str) or not code:
                if detail == "admin account is inactive":
                    code = "ADMIN_ACCOUNT_INACTIVE"
                else:
                    code = "ADMIN_API_ERROR"
            if not isinstance(message, str) or not message:
                message = str(detail or "请求失败")
            raise AdminApiRequestError(
                status_code=response.status_code,
                code=code,
                message=message,
            )
        return payload
