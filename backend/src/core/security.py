"""JWT-style access token utilities for student and admin sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from src.core.settings import Settings
from src.models.admin_user import AdminUser
from src.models.student_user import StudentUser


class AccessTokenError(ValueError):
    """Base error for access token creation and validation."""


class InvalidAccessTokenError(AccessTokenError):
    """Raised when a token cannot be parsed or verified."""


class ExpiredAccessTokenError(AccessTokenError):
    """Raised when a token has passed its `exp` timestamp."""


class AccessTokenService:
    """Create and verify lightweight HS256 JWT access tokens."""

    def __init__(self, settings: Settings, *, issuer: str = "xinyu-backend") -> None:
        self._secret = settings.jwt_secret_key.get_secret_value().encode("utf-8")
        self._issuer = issuer

    def issue_student_access_token(
        self,
        student: StudentUser,
        *,
        expires_in_seconds: int = 7 * 24 * 60 * 60,
    ) -> str:
        """Issue an access token for the authenticated student."""
        issued_at = int(time.time())
        payload = {
            "sub": f"student:{student.id}",
            "student_id": student.id,
            "role": "student",
            "is_demo": student.is_demo,
            "consent_status": student.consent_status.value,
            "iat": issued_at,
            "exp": issued_at + expires_in_seconds,
            "iss": self._issuer,
        }
        return self._encode_token(payload)

    def issue_admin_access_token(
        self,
        admin: AdminUser,
        *,
        expires_in_seconds: int = 12 * 60 * 60,
    ) -> str:
        """Issue an access token for the authenticated administrator."""
        issued_at = int(time.time())
        payload = {
            "sub": f"admin:{admin.id}",
            "admin_id": admin.id,
            "role": "admin",
            "username": admin.username,
            "role_code": admin.role_code.value,
            "iat": issued_at,
            "exp": issued_at + expires_in_seconds,
            "iss": self._issuer,
        }
        return self._encode_token(payload)

    def decode_access_token(
        self,
        token: str,
        *,
        expected_role: str | None = None,
    ) -> dict[str, Any]:
        """Decode and verify a previously issued access token."""
        header_segment, payload_segment, signature_segment = self._split_token(token)
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        expected_signature = self._sign(signing_input)
        actual_signature = self._decode_segment(signature_segment)
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise InvalidAccessTokenError("token signature is invalid")

        header = self._load_segment_json(header_segment)
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise InvalidAccessTokenError("token header is invalid")

        payload = self._load_segment_json(payload_segment)
        if payload.get("iss") != self._issuer:
            raise InvalidAccessTokenError("token issuer is invalid")

        expires_at = payload.get("exp")
        if not isinstance(expires_at, int):
            raise InvalidAccessTokenError("token expiration is missing")
        if expires_at < int(time.time()):
            raise ExpiredAccessTokenError("token has expired")

        if expected_role is not None and payload.get("role") != expected_role:
            raise InvalidAccessTokenError("token role is invalid")

        return payload

    def _encode_token(self, payload: dict[str, Any]) -> str:
        """Encode a JWT-style token using HS256."""
        header = {"alg": "HS256", "typ": "JWT"}
        header_segment = self._encode_segment(header)
        payload_segment = self._encode_segment(payload)
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        signature_segment = self._encode_bytes(self._sign(signing_input))
        return f"{header_segment}.{payload_segment}.{signature_segment}"

    def _sign(self, signing_input: bytes) -> bytes:
        """Create an HMAC SHA-256 signature for one token input."""
        return hmac.new(self._secret, signing_input, hashlib.sha256).digest()

    def _split_token(self, token: str) -> tuple[str, str, str]:
        """Split a token into the expected three JWT segments."""
        segments = token.split(".")
        if len(segments) != 3:
            raise InvalidAccessTokenError("token must contain three segments")
        return segments[0], segments[1], segments[2]

    def _load_segment_json(self, segment: str) -> dict[str, Any]:
        """Decode one token segment and parse it as JSON."""
        try:
            payload = json.loads(self._decode_segment(segment).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidAccessTokenError("token segment is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise InvalidAccessTokenError("token segment must decode to an object")
        return payload

    def _encode_segment(self, payload: dict[str, Any]) -> str:
        """Serialize and base64url-encode one JSON token segment."""
        return self._encode_bytes(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )

    def _encode_bytes(self, value: bytes) -> str:
        """Encode raw bytes using URL-safe base64 without padding."""
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def _decode_segment(self, value: str) -> bytes:
        """Decode one URL-safe base64 token segment."""
        padding = "=" * (-len(value) % 4)
        try:
            return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise InvalidAccessTokenError("token segment is not valid base64") from exc
