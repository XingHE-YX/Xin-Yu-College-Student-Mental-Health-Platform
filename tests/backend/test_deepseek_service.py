"""Tests for the DeepSeek JSON chat completion client."""

from __future__ import annotations

import json
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
    assert result.fallback_used is False
    assert result.fallback_reason is None


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


def build_timeout_client():
    """Return one fake httpx client class that raises a timeout."""

    class FakeClient:
        def __init__(self, *, timeout, headers) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url, json):
            raise httpx.ReadTimeout(
                "timed out",
                request=httpx.Request("POST", url),
            )

    return FakeClient


def build_status_error_client():
    """Return one fake httpx client class that raises a non-2xx status error."""

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

    return FakeClient


def build_invalid_content_client():
    """Return one fake httpx client class that returns non-JSON completion content."""

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
                    "id": "chatcmpl-test-004",
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

    return FakeClient


@pytest.mark.parametrize(
    ("client_factory", "expected_reason_fragment"),
    [
        (
            lambda: build_timeout_client(),
            "timed out",
        ),
        (
            lambda: build_status_error_client(),
            "non-success status",
        ),
        (
            lambda: build_invalid_content_client(),
            "not valid JSON",
        ),
    ],
)
def test_create_json_completion_with_fallback_uses_local_mock_response(
    monkeypatch,
    tmp_path,
    client_factory,
    expected_reason_fragment: str,
) -> None:
    """Supported upstream failures should fall back to the local mock JSON object."""
    mock_response_path = tmp_path / "mock_response.json"
    mock_payload = {
        "risk_level": "low",
        "risk_score": 0.12,
        "emotion_tags": ["fatigue"],
        "trigger_phrases": [],
        "reason_text": "mocked fallback response",
        "recommended_action": "publish",
    }
    mock_response_path.write_text(
        json.dumps(mock_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.services.deepseek_service.httpx.Client",
        client_factory(),
    )

    result = DeepSeekService(build_settings()).create_json_completion_with_fallback(
        system_prompt="Analyze treehole safety risk.",
        user_prompt="I feel overwhelmed.",
        response_example={"risk_level": "low"},
        mock_response_path=mock_response_path,
    )

    assert result.fallback_used is True
    assert expected_reason_fragment in (result.fallback_reason or "")
    assert result.finish_reason == "mock_fallback"
    assert result.content_json == mock_payload
    assert result.response_payload["source"] == "mock_response.json"
    assert result.response_payload["mock_response_path"] == str(mock_response_path)


def test_create_json_completion_with_fallback_raises_when_mock_file_is_invalid(
    monkeypatch,
    tmp_path,
) -> None:
    """The fallback wrapper should fail clearly when the local mock file is malformed."""
    mock_response_path = tmp_path / "mock_response.json"
    mock_response_path.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr(
        "src.services.deepseek_service.httpx.Client",
        build_timeout_client(),
    )

    with pytest.raises(
        DeepSeekServiceError,
        match="mock fallback file is not valid JSON",
    ):
        DeepSeekService(build_settings()).create_json_completion_with_fallback(
            system_prompt="Analyze treehole safety risk.",
            user_prompt="I feel overwhelmed.",
            response_example={"risk_level": "low"},
            mock_response_path=mock_response_path,
        )
