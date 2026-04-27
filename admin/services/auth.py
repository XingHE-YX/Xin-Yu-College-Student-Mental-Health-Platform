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

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform one backend request and normalize error handling."""
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(
                    method,
                    f"{self.api_base_url}{path}",
                    headers=headers,
                    json=json,
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
