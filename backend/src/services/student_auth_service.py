"""Student login service for WeChat and demo-mode authentication."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.core.security import AccessTokenService
from src.core.settings import Settings
from src.models.base import utc_now
from src.models.student_user import StudentUser
from src.repositories.student_user_repository import StudentUserRepository
from src.schemas.student_auth import StudentWechatLoginRequest
from src.services.wechat_session_service import WeChatSessionService

DEFAULT_COLLEGE_NAME = "待完善学院"
DEFAULT_CLASS_NAME = "待完善班级"
DEMO_PHONE_NUMBER = "+8613900000001"
DEMO_OPENID = "demo-student-openid"
DEMO_COLLEGE_NAME = "演示学院"
DEMO_CLASS_NAME = "2026级演示班"
DEMO_NICKNAME = "Quiet Ginkgo"
PHONE_PATTERN = re.compile(r"^\+?\d{6,20}$")
NICKNAME_ADJECTIVES = (
    "Quiet",
    "Soft",
    "Calm",
    "Gentle",
    "Warm",
    "Clear",
    "Still",
    "Kind",
    "Steady",
    "Mild",
)
NICKNAME_NOUNS = (
    "Ginkgo",
    "Cedar",
    "Willow",
    "Harbor",
    "Maple",
    "Cloud",
    "River",
    "Breeze",
    "Dawn",
    "Moss",
)


class StudentAuthError(ValueError):
    """Base error for student login flows."""


class InvalidPhoneTicketError(StudentAuthError):
    """Raised when the provided phone ticket cannot be parsed."""


class StudentLoginConflictError(StudentAuthError):
    """Raised when phone and openid map to different student rows."""


class DemoLoginDisabledError(StudentAuthError):
    """Raised when demo login is disabled by runtime configuration."""


@dataclass(frozen=True, slots=True)
class PhoneTicketProfile:
    """Normalized phone-ticket data used during login."""

    phone_e164: str
    college_name: str | None = None
    class_name: str | None = None


@dataclass(frozen=True, slots=True)
class StudentLoginResult:
    """A successful student login outcome."""

    access_token: str
    student: StudentUser


class StudentAuthService:
    """Authenticate student users through WeChat or demo mode."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings,
        token_service: AccessTokenService,
        wechat_session_service: WeChatSessionService,
    ) -> None:
        self.session = session
        self.settings = settings
        self.token_service = token_service
        self.wechat_session_service = wechat_session_service
        self.repository = StudentUserRepository(session)

    def login_with_wechat(
        self,
        payload: StudentWechatLoginRequest,
    ) -> StudentLoginResult:
        """Create or refresh a student session from WeChat login data."""
        wechat_session = self.wechat_session_service.exchange_login_code(
            payload.login_code
        )
        phone_profile = self._parse_phone_ticket(payload.phone_ticket)
        student = self._create_or_update_student(
            phone_e164=phone_profile.phone_e164,
            wechat_openid=wechat_session.openid,
            college_name=phone_profile.college_name,
            class_name=phone_profile.class_name,
            is_demo=False,
            demo_nickname=None,
        )
        access_token = self.token_service.issue_student_access_token(student)
        return StudentLoginResult(access_token=access_token, student=student)

    def login_demo_student(self) -> StudentLoginResult:
        """Create or refresh the fixed demo student account."""
        if not self.settings.enable_demo_login:
            raise DemoLoginDisabledError("demo login is disabled")

        student = self._create_or_update_student(
            phone_e164=DEMO_PHONE_NUMBER,
            wechat_openid=DEMO_OPENID,
            college_name=DEMO_COLLEGE_NAME,
            class_name=DEMO_CLASS_NAME,
            is_demo=True,
            demo_nickname=DEMO_NICKNAME,
        )
        access_token = self.token_service.issue_student_access_token(student)
        return StudentLoginResult(access_token=access_token, student=student)

    def _create_or_update_student(
        self,
        *,
        phone_e164: str,
        wechat_openid: str,
        college_name: str | None,
        class_name: str | None,
        is_demo: bool,
        demo_nickname: str | None,
    ) -> StudentUser:
        """Upsert a student while respecting unique phone/openid constraints."""
        student_by_phone = self.repository.get_by_phone(phone_e164)
        student_by_openid = self.repository.get_by_wechat_openid(wechat_openid)
        if (
            student_by_phone is not None
            and student_by_openid is not None
            and student_by_phone.id != student_by_openid.id
        ):
            raise StudentLoginConflictError(
                "phone number and WeChat openid map to different students"
            )

        login_at = utc_now()
        student = student_by_phone or student_by_openid
        if student is None:
            seed_source = wechat_openid if not is_demo else DEMO_OPENID
            display_nickname = demo_nickname or self._build_display_nickname(seed_source)
            display_avatar_seed = self._build_avatar_seed(seed_source)
            student = self.repository.create_student(
                phone_e164=phone_e164,
                wechat_openid=wechat_openid,
                display_nickname=display_nickname,
                display_avatar_seed=display_avatar_seed,
                college_name=college_name or DEFAULT_COLLEGE_NAME,
                class_name=class_name or DEFAULT_CLASS_NAME,
                is_demo=is_demo,
                last_login_at=login_at,
            )
        else:
            self.repository.update_login_fields(
                student,
                phone_e164=phone_e164,
                wechat_openid=wechat_openid,
                college_name=college_name,
                class_name=class_name,
                last_login_at=login_at,
            )
            student.is_demo = is_demo

        self.session.commit()
        self.session.refresh(student)
        return student

    def _parse_phone_ticket(self, phone_ticket: str) -> PhoneTicketProfile:
        """Parse a flexible phone-ticket payload for MVP login flows."""
        raw_ticket = phone_ticket.strip()
        payload = self._decode_phone_ticket_payload(raw_ticket)
        if isinstance(payload, dict):
            raw_phone = payload.get("phone_number") or payload.get("phone_e164")
            if not isinstance(raw_phone, str) or not raw_phone.strip():
                raise InvalidPhoneTicketError("phone ticket is missing phone_number")
            return PhoneTicketProfile(
                phone_e164=self._normalize_phone_number(raw_phone),
                college_name=self._clean_optional_text(payload.get("college_name")),
                class_name=self._clean_optional_text(payload.get("class_name")),
            )

        if isinstance(payload, str):
            return PhoneTicketProfile(
                phone_e164=self._normalize_phone_number(payload),
                college_name=None,
                class_name=None,
            )

        raise InvalidPhoneTicketError("phone ticket payload format is unsupported")

    def _decode_phone_ticket_payload(self, phone_ticket: str) -> dict[str, Any] | str:
        """Decode a raw or base64url-encoded phone ticket."""
        direct_payload = self._parse_json_text(phone_ticket)
        if direct_payload is not None:
            return direct_payload

        if PHONE_PATTERN.match(phone_ticket):
            return phone_ticket

        decoded_text = self._decode_base64url_text(phone_ticket)
        if decoded_text is not None:
            decoded_payload = self._parse_json_text(decoded_text)
            if decoded_payload is not None:
                return decoded_payload
            if PHONE_PATTERN.match(decoded_text):
                return decoded_text

        raise InvalidPhoneTicketError("phone ticket is not a valid JSON or phone string")

    def _parse_json_text(self, value: str) -> dict[str, Any] | str | None:
        """Parse JSON text when the ticket is already plain UTF-8."""
        if not value.startswith(("{", '"')):
            return None
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, (dict, str)):
            return payload
        raise InvalidPhoneTicketError("phone ticket JSON must decode to an object or string")

    def _decode_base64url_text(self, value: str) -> str | None:
        """Decode URL-safe base64 text and return UTF-8 content when possible."""
        padding = "=" * (-len(value) % 4)
        try:
            decoded_bytes = base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            return None

        try:
            return decoded_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidPhoneTicketError(
                "phone ticket base64 payload is not valid UTF-8"
            ) from exc

    def _normalize_phone_number(self, raw_phone: str) -> str:
        """Normalize mainland China phone strings into E.164-like format."""
        digits_only = re.sub(r"\D", "", raw_phone)
        if not digits_only:
            raise InvalidPhoneTicketError("phone ticket does not contain digits")

        if raw_phone.startswith("+") and 6 <= len(digits_only) <= 15:
            return f"+{digits_only}"
        if len(digits_only) == 11 and digits_only.startswith("1"):
            return f"+86{digits_only}"
        if len(digits_only) == 13 and digits_only.startswith("86"):
            return f"+{digits_only}"
        if 6 <= len(digits_only) <= 15:
            return f"+{digits_only}"
        raise InvalidPhoneTicketError("phone number format is invalid")

    def _clean_optional_text(self, value: Any) -> str | None:
        """Trim optional string metadata from phone tickets."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise InvalidPhoneTicketError("phone ticket metadata must be text")
        cleaned = value.strip()
        return cleaned or None

    def _build_display_nickname(self, seed_source: str) -> str:
        """Create a calm anonymous nickname derived from stable user identity."""
        seed_value = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest(), 16)
        adjective = NICKNAME_ADJECTIVES[seed_value % len(NICKNAME_ADJECTIVES)]
        noun = NICKNAME_NOUNS[
            (seed_value // len(NICKNAME_ADJECTIVES)) % len(NICKNAME_NOUNS)
        ]
        return f"{adjective} {noun}"

    def _build_avatar_seed(self, seed_source: str) -> str:
        """Create a stable avatar seed for frontend anonymous avatar generation."""
        digest = hashlib.sha256(seed_source.encode("utf-8")).hexdigest()
        return f"student-{digest[:16]}"
