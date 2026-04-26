"""Tests for the DeepSeek JSON chat completion client."""

from __future__ import annotations

import httpx
import pytest

from src.core.settings import Settings
from src.services.deepseek_service import (
    DEEPSEEK_CHAT_COMPLETIONS_URL,
    DEEPSEEK_MODEL_NAME,
    DeepSeekService,
    DeepSeekServiceError,
)


def build_settings() -> Settings:
    """Create runtime settings for isolated DeepSeek client tests."""
    return Settings(
        APP_NAME="心语 DeepSeek 测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def test_create_json_completion_posts_to_deepseek_and_parses_json(monkeypatch) -> None:
    """The client should enforce JSON mode and decode the model content."""
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, timeout, headers) -> None:
            captured["timeout"] = timeout
            captured["headers"] = headers

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={
                    "id": "chatcmpl-test-001",
                    "model": DEEPSEEK_MODEL_NAME,
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": (
                                    '{"risk_level":"low","reason_text":"tone is neutral"}'
                                )
                            },
                        }
                    ],
                },
            )

    monkeypatch.setattr("src.services.deepseek_service.httpx.Client", FakeClient)

    result = DeepSeekService(build_settings()).create_json_completion(
        system_prompt="Analyze treehole safety risk.",
        user_prompt="I feel tired but safe.",
        response_example={
            "risk_level": "low",
            "reason_text": "brief rationale",
        },
    )

    assert captured["url"] == DEEPSEEK_CHAT_COMPLETIONS_URL
    assert captured["timeout"] == 20.0
    assert captured["headers"] == {
        "Authorization": "Bearer deepseek-test-key",
        "Content-Type": "application/json",
    }
    request_payload = captured["json"]
    assert isinstance(request_payload, dict)
    assert request_payload["model"] == DEEPSEEK_MODEL_NAME
    assert request_payload["response_format"] == {"type": "json_object"}
    assert "JSON" in request_payload["messages"][0]["content"]
    assert '"risk_level": "low"' in request_payload["messages"][0]["content"]
    assert request_payload["messages"][1]["content"] == "I feel tired but safe."

    assert result.completion_id == "chatcmpl-test-001"
    assert result.model_name == DEEPSEEK_MODEL_NAME
    assert result.finish_reason == "stop"
    assert result.content_json == {
        "risk_level": "low",
        "reason_text": "tone is neutral",
    }


def test_create_json_completion_raises_on_http_failure(monkeypatch) -> None:
    """Non-success HTTP responses should raise a service-level error."""

    class FakeClient:
        def __init__(self, *, timeout, headers) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url, json):
            response = httpx.Response(
                status_code=503,
                request=httpx.Request("POST", url),
                json={"error": {"message": "upstream unavailable"}},
            )
            response.raise_for_status()

    monkeypatch.setattr("src.services.deepseek_service.httpx.Client", FakeClient)

    with pytest.raises(
        DeepSeekServiceError,
        match="non-success status",
    ):
        DeepSeekService(build_settings()).create_json_completion(
            system_prompt="Analyze treehole safety risk.",
            user_prompt="I feel unsafe.",
            response_example={"risk_level": "high"},
        )


def test_create_json_completion_raises_on_non_json_content(monkeypatch) -> None:
    """String content that is not valid JSON should be rejected."""

    class FakeClient:
        def __init__(self, *, timeout, headers) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url, json):
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={
                    "id": "chatcmpl-test-002",
                    "model": DEEPSEEK_MODEL_NAME,
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": "not json",
                            },
                        }
                    ],
                },
            )

    monkeypatch.setattr("src.services.deepseek_service.httpx.Client", FakeClient)

    with pytest.raises(
        DeepSeekServiceError,
        match="not valid JSON",
    ):
        DeepSeekService(build_settings()).create_json_completion(
            system_prompt="Analyze treehole safety risk.",
            user_prompt="I feel lost.",
            response_example={"risk_level": "watch"},
        )


def test_create_json_completion_raises_on_non_object_json(monkeypatch) -> None:
    """JSON mode should still reject arrays and other non-object payloads."""

    class FakeClient:
        def __init__(self, *, timeout, headers) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url, json):
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={
                    "id": "chatcmpl-test-003",
                    "model": DEEPSEEK_MODEL_NAME,
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": '["unexpected", "array"]',
                            },
                        }
                    ],
                },
            )

    monkeypatch.setattr("src.services.deepseek_service.httpx.Client", FakeClient)

    with pytest.raises(
        DeepSeekServiceError,
        match="JSON object",
    ):
        DeepSeekService(build_settings()).create_json_completion(
            system_prompt="Analyze treehole safety risk.",
            user_prompt="I feel uncertain.",
            response_example={"risk_level": "low"},
        )
