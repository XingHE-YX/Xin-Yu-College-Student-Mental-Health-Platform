"""DeepSeek chat completion service for structured JSON output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from src.core.settings import Settings

DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL_NAME = "deepseek-chat"
DEFAULT_DEEPSEEK_MOCK_RESPONSE_PATH = (
    Path(__file__).resolve().parents[2] / "mock_response.json"
)
HIGH_RISK_KEYWORDS = (
    "不想活了",
    "不想继续了",
    "结束这一切",
    "结束生命",
    "跳下去",
    "跳楼",
    "割腕",
    "轻生",
    "自杀",
    "想死",
    "kill myself",
    "end it all",
    "suicide",
    "hurt myself",
)
WATCH_RISK_KEYWORDS = (
    "撑不住",
    "压力很大",
    "胸口发闷",
    "不想说话",
    "睡不着",
    "睡不太着",
    "很累",
    "焦虑",
    "崩溃",
    "难受",
    "想哭",
)


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
    fallback_used: bool
    fallback_reason: str | None


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
        request_payload = self._build_request_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_example=response_example,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._execute_json_completion(request_payload)

    def create_json_completion_with_fallback(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_example: dict[str, Any],
        temperature: float = 0.2,
        max_tokens: int = 800,
        mock_response_path: str | Path | None = None,
    ) -> DeepSeekJsonCompletionResult:
        """Return one JSON completion, falling back to local mock data on supported failures."""
        request_payload = self._build_request_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_example=response_example,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if self.settings.enable_mock_ai:
            return self._load_mock_completion(
                request_payload=request_payload,
                fallback_reason="mock AI enabled by runtime setting",
                mock_response_path=mock_response_path,
            )
        try:
            return self._execute_json_completion(request_payload)
        except DeepSeekServiceError as exc:
            return self._load_mock_completion(
                request_payload=request_payload,
                fallback_reason=str(exc),
                mock_response_path=mock_response_path,
            )

    def _build_request_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_example: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Build the stable DeepSeek request payload used by all JSON completions."""
        normalized_system_prompt = system_prompt.strip()
        normalized_user_prompt = user_prompt.strip()
        if not normalized_system_prompt:
            raise ValueError("system_prompt must not be blank")
        if not normalized_user_prompt:
            raise ValueError("user_prompt must not be blank")
        if not response_example:
            raise ValueError("response_example must not be empty")

        return {
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

    def _execute_json_completion(
        self,
        request_payload: dict[str, Any],
    ) -> DeepSeekJsonCompletionResult:
        """Execute one remote DeepSeek request and parse the JSON completion result."""
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
        except httpx.TimeoutException as exc:
            raise DeepSeekServiceError("DeepSeek chat completion timed out") from exc
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
            fallback_used=False,
            fallback_reason=None,
        )

    def _load_mock_completion(
        self,
        *,
        request_payload: dict[str, Any],
        fallback_reason: str,
        mock_response_path: str | Path | None,
    ) -> DeepSeekJsonCompletionResult:
        """Load one local mock response used when the upstream API cannot complete."""
        resolved_path = (
            Path(mock_response_path)
            if mock_response_path is not None
            else DEFAULT_DEEPSEEK_MOCK_RESPONSE_PATH
        )
        try:
            content_json = json.loads(resolved_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DeepSeekServiceError(
                f"DeepSeek mock fallback file does not exist: {resolved_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise DeepSeekServiceError(
                "DeepSeek mock fallback file is not valid JSON"
            ) from exc

        if not isinstance(content_json, dict):
            raise DeepSeekServiceError(
                "DeepSeek mock fallback content must decode to a JSON object"
            )

        content_json = self._build_mock_content_json(
            base_content_json=content_json,
            request_payload=request_payload,
        )
        content_text = json.dumps(content_json, ensure_ascii=False)
        return DeepSeekJsonCompletionResult(
            request_payload=request_payload,
            response_payload={
                "source": "mock_response.json",
                "mock_response_path": str(resolved_path),
                "fallback_reason": fallback_reason,
                "mock_mode": (
                    "forced_enabled" if self.settings.enable_mock_ai else "fallback"
                ),
                "mock_classification": self._classify_mock_prompt(request_payload)[0],
                "content": content_json,
            },
            completion_id=None,
            model_name=DEEPSEEK_MODEL_NAME,
            finish_reason="mock_fallback",
            content_text=content_text,
            content_json=content_json,
            fallback_used=True,
            fallback_reason=fallback_reason,
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

    def _build_mock_content_json(
        self,
        *,
        base_content_json: dict[str, Any],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Build one local mock result, upgrading severity from prompt keywords when needed."""
        classification, trigger_phrases = self._classify_mock_prompt(request_payload)
        if classification == "high":
            return {
                **base_content_json,
                "risk_level": "high",
                "risk_score": 0.95,
                "emotion_tags": ["despair", "crisis"],
                "trigger_phrases": trigger_phrases,
                "reason_text": "本地模拟分析检测到明确高风险表达，需要优先人工复核。",
                "recommended_action": "manual_review_high",
            }
        if classification == "watch":
            return {
                **base_content_json,
                "risk_level": "watch",
                "risk_score": 0.64,
                "emotion_tags": ["stress", "fatigue"],
                "trigger_phrases": trigger_phrases,
                "reason_text": "本地模拟分析检测到持续性压力或退缩表达，建议继续关注。",
                "recommended_action": "focus_list",
            }
        return base_content_json

    def _classify_mock_prompt(
        self,
        request_payload: dict[str, Any],
    ) -> tuple[str, list[str]]:
        """Classify the prompt into low/watch/high using deterministic local keywords."""
        prompt_text = self._extract_mock_prompt_text(request_payload).casefold()
        high_triggers = self._collect_matching_keywords(prompt_text, HIGH_RISK_KEYWORDS)
        if high_triggers:
            return "high", high_triggers

        watch_triggers = self._collect_matching_keywords(prompt_text, WATCH_RISK_KEYWORDS)
        if watch_triggers:
            return "watch", watch_triggers
        return "low", []

    def _extract_mock_prompt_text(
        self,
        request_payload: dict[str, Any],
    ) -> str:
        """Extract the user prompt text from one normalized DeepSeek request payload."""
        messages = request_payload.get("messages", [])
        if not isinstance(messages, list):
            return ""
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                return content
        return ""

    def _collect_matching_keywords(
        self,
        prompt_text: str,
        keywords: tuple[str, ...],
    ) -> list[str]:
        """Return matched keywords in declaration order without duplicates."""
        matched_keywords: list[str] = []
        for keyword in keywords:
            if keyword.casefold() not in prompt_text:
                continue
            if keyword not in matched_keywords:
                matched_keywords.append(keyword)
        return matched_keywords
