"""Administrator authentication and session issuance services."""

from __future__ import annotations

from dataclasses import dataclass

from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from sqlalchemy.orm import Session

from src.constants.workflow_enums import AuditActorType
from src.core.security import AccessTokenService
from src.models.admin_user import AdminUser
from src.models.audit_log import AuditLog
from src.models.base import utc_now
from src.repositories.admin_user_repository import AdminUserRepository
from src.repositories.review_workflow_repository import ReviewWorkflowRepository

PASSWORD_HASHER = PasswordHash.recommended()


class AdminAuthError(ValueError):
    """Base error raised when administrator authentication fails."""


class InvalidAdminCredentialsError(AdminAuthError):
    """Raised when the submitted username or password is incorrect."""


class AdminAccountInactiveError(AdminAuthError):
    """Raised when an inactive administrator attempts to log in."""


@dataclass(frozen=True, slots=True)
class AdminLoginResult:
    """Authenticated administrator session payload."""

    admin: AdminUser
    access_token: str


class AdminAuthService:
    """Validate admin credentials, issue JWTs, and audit successful logins."""

    def __init__(
        self,
        session: Session,
        *,
        token_service: AccessTokenService,
    ) -> None:
        self.session = session
        self.token_service = token_service
        self.admin_repository = AdminUserRepository(session)
        self.review_repository = ReviewWorkflowRepository(session)

    def login(
        self,
        *,
        username: str,
        password: str,
        ip_address: str | None = None,
    ) -> AdminLoginResult:
        """Authenticate one active administrator and issue an access token."""
        normalized_username = username.strip()
        admin = self.admin_repository.get_by_username(normalized_username)
        if admin is None or not self._verify_password(password, admin.password_hash):
            raise InvalidAdminCredentialsError("username or password is incorrect")
        if not admin.is_active:
            raise AdminAccountInactiveError("administrator account is inactive")

        logged_in_at = utc_now()
        self.admin_repository.update_last_login_at(admin, last_login_at=logged_in_at)
        self.review_repository.add_audit_log(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                actor_id=admin.id,
                action_code="ADMIN_LOGIN_SUCCESS",
                target_type="admin_user",
                target_id=admin.id,
                metadata_json={
                    "role_code": admin.role_code.value,
                    "username": admin.username,
                },
                ip_address=ip_address,
            )
        )
        access_token = self.token_service.issue_admin_access_token(admin)
        self.session.commit()
        self.session.refresh(admin)
        return AdminLoginResult(admin=admin, access_token=access_token)

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Return whether one plaintext password matches the stored Argon2 hash."""
        try:
            return PASSWORD_HASHER.verify(password, password_hash)
        except PwdlibError:
            return False
