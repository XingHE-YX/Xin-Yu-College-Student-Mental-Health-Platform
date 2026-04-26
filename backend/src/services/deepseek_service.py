"""DeepSeek chat completion service for structured JSON output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from src.core.settings import Settings

DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL_NAME = "deepseek-chat"


class DeepSeekServiceError(RuntimeError):
    """Raised when the DeepSeek API cannot return a usable JSON completion."""


@dataclass(frozen=True, slots=True)
class DeepSeekJsonCompletionResult:
    """Normalized structured output returned by one DeepSeek chat completion."""

    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    completion_id: str | None
    model_name: str | None
    finish_reason: str | None
    content_text: str
    content_json: dict[str, Any]


class DeepSeekService:
    """Call the DeepSeek chat completion API and require JSON output."""

    def __init__(self, settings: Settings, *, timeout_seconds: float = 20.0) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    def create_json_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_example: dict[str, Any],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> DeepSeekJsonCompletionResult:
        """Request one DeepSeek chat completion that must decode into a JSON object."""
        normalized_system_prompt = system_prompt.strip()
        normalized_user_prompt = user_prompt.strip()
        if not normalized_system_prompt:
            raise ValueError("system_prompt must not be blank")
        if not normalized_user_prompt:
            raise ValueError("user_prompt must not be blank")
        if not response_example:
            raise ValueError("response_example must not be empty")

        request_payload = {
            "model": DEEPSEEK_MODEL_NAME,
            "messages": [
                {
                    "role": "system",
                    "content": self._build_json_system_prompt(
                        normalized_system_prompt,
                        response_example,
                    ),
                },
                {
                    "role": "user",
                    "content": normalized_user_prompt,
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": (
                f"Bearer {self.settings.deepseek_api_key.get_secret_value()}"
            ),
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds, headers=headers) as client:
                response = client.post(
                    DEEPSEEK_CHAT_COMPLETIONS_URL,
                    json=request_payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise DeepSeekServiceError(
                "DeepSeek chat completion returned a non-success status"
            ) from exc
        except httpx.HTTPError as exc:
            raise DeepSeekServiceError(
                "failed to reach DeepSeek chat completion API"
            ) from exc

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise DeepSeekServiceError(
                "DeepSeek chat completion returned invalid JSON"
            ) from exc

        if not isinstance(response_payload, dict):
            raise DeepSeekServiceError(
                "DeepSeek chat completion returned an invalid payload"
            )

        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DeepSeekServiceError(
                "DeepSeek chat completion payload is missing choices"
            )

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise DeepSeekServiceError(
                "DeepSeek chat completion payload contains an invalid choice"
            )

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise DeepSeekServiceError(
                "DeepSeek chat completion payload is missing message content"
            )

        content_text = message.get("content")
        if not isinstance(content_text, str) or not content_text.strip():
            raise DeepSeekServiceError(
                "DeepSeek chat completion returned empty content"
            )

        try:
            content_json = json.loads(content_text)
        except json.JSONDecodeError as exc:
            raise DeepSeekServiceError(
                "DeepSeek chat completion content is not valid JSON"
            ) from exc

        if not isinstance(content_json, dict):
            raise DeepSeekServiceError(
                "DeepSeek chat completion content must decode to a JSON object"
            )

        completion_id = response_payload.get("id")
        model_name = response_payload.get("model")
        finish_reason = first_choice.get("finish_reason")

        return DeepSeekJsonCompletionResult(
            request_payload=request_payload,
            response_payload=response_payload,
            completion_id=completion_id if isinstance(completion_id, str) else None,
            model_name=model_name if isinstance(model_name, str) else None,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            content_text=content_text,
            content_json=content_json,
        )

    def _build_json_system_prompt(
        self,
        system_prompt: str,
        response_example: dict[str, Any],
    ) -> str:
        """Append stable JSON-output instructions required by DeepSeek JSON mode."""
        response_example_json = json.dumps(
            response_example,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return (
            f"{system_prompt}\n\n"
            "You must reply in valid JSON only.\n"
            "Return exactly one JSON object and do not wrap it in markdown.\n"
            "Use the following JSON example as the required output shape:\n"
            f"{response_example_json}"
        )
