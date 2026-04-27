"""Repository helpers for administrator authentication flows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.admin_user import AdminUser


class AdminUserRepository:
    """Persist and query administrator accounts needed by auth services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, admin_user_id: int) -> AdminUser | None:
        """Return one administrator by primary key."""
        return self.session.get(AdminUser, admin_user_id)

    def get_by_username(self, username: str) -> AdminUser | None:
        """Return one administrator by unique username."""
        statement = select(AdminUser).where(AdminUser.username == username)
        return self.session.scalar(statement)

    def update_last_login_at(
        self,
        admin: AdminUser,
        *,
        last_login_at: datetime,
    ) -> AdminUser:
        """Persist the administrator's latest successful login timestamp."""
        admin.last_login_at = last_login_at
        self.session.flush()
        return admin
