"""WeChat session exchange service for student login."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.core.settings import Settings

WECHAT_JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WeChatSessionExchangeError(RuntimeError):
    """Raised when WeChat session exchange fails."""


@dataclass(frozen=True, slots=True)
class WeChatSession:
    """Normalized WeChat session payload used by auth services."""

    openid: str
    session_key: str
    unionid: str | None = None


class WeChatSessionService:
    """Exchange a mini-program login code for WeChat session metadata."""

    def __init__(self, settings: Settings, *, timeout_seconds: float = 10.0) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    def exchange_login_code(self, login_code: str) -> WeChatSession:
        """Call WeChat's `jscode2session` API and normalize the response."""
        params = {
            "appid": self.settings.wechat_app_id,
            "secret": self.settings.wechat_app_secret.get_secret_value(),
            "js_code": login_code,
            "grant_type": "authorization_code",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(WECHAT_JSCODE2SESSION_URL, params=params)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WeChatSessionExchangeError(
                "failed to reach WeChat session exchange API"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise WeChatSessionExchangeError(
                "WeChat session exchange returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise WeChatSessionExchangeError(
                "WeChat session exchange returned an invalid payload"
            )

        error_code = payload.get("errcode")
        if error_code not in {None, 0}:
            error_message = payload.get("errmsg", "unknown WeChat auth error")
            raise WeChatSessionExchangeError(
                f"WeChat session exchange failed: {error_code} {error_message}"
            )

        openid = payload.get("openid")
        session_key = payload.get("session_key")
        unionid = payload.get("unionid")
        if not isinstance(openid, str) or not openid:
            raise WeChatSessionExchangeError(
                "WeChat session exchange payload is missing openid"
            )
        if not isinstance(session_key, str) or not session_key:
            raise WeChatSessionExchangeError(
                "WeChat session exchange payload is missing session_key"
            )
        if unionid is not None and not isinstance(unionid, str):
            raise WeChatSessionExchangeError(
                "WeChat session exchange payload contains an invalid unionid"
            )

        return WeChatSession(
            openid=openid,
            session_key=session_key,
            unionid=unionid,
        )
