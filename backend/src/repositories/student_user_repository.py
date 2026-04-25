"""Repository helpers for student account authentication flows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.account_enums import ConsentStatus
from src.models.student_user import StudentUser


class StudentUserRepository:
    """Persist and query student user records needed by auth services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, student_id: int) -> StudentUser | None:
        """Return one student by primary key."""
        return self.session.get(StudentUser, student_id)

    def get_by_phone(self, phone_e164: str) -> StudentUser | None:
        """Return one student by phone number."""
        statement = select(StudentUser).where(StudentUser.phone_e164 == phone_e164)
        return self.session.scalar(statement)

    def get_by_wechat_openid(self, wechat_openid: str) -> StudentUser | None:
        """Return one student by WeChat openid."""
        statement = select(StudentUser).where(StudentUser.wechat_openid == wechat_openid)
        return self.session.scalar(statement)

    def create_student(
        self,
        *,
        phone_e164: str,
        wechat_openid: str,
        display_nickname: str,
        display_avatar_seed: str,
        college_name: str,
        class_name: str,
        is_demo: bool,
        last_login_at: datetime,
    ) -> StudentUser:
        """Insert a new student account."""
        student = StudentUser(
            phone_e164=phone_e164,
            wechat_openid=wechat_openid,
            display_nickname=display_nickname,
            display_avatar_seed=display_avatar_seed,
            college_name=college_name,
            class_name=class_name,
            consent_status=ConsentStatus.MISSING,
            is_demo=is_demo,
            last_login_at=last_login_at,
        )
        self.session.add(student)
        self.session.flush()
        return student

    def update_login_fields(
        self,
        student: StudentUser,
        *,
        phone_e164: str,
        wechat_openid: str,
        college_name: str | None,
        class_name: str | None,
        last_login_at: datetime,
    ) -> StudentUser:
        """Refresh mutable login fields for a returning student."""
        student.phone_e164 = phone_e164
        student.wechat_openid = wechat_openid
        if college_name:
            student.college_name = college_name
        if class_name:
            student.class_name = class_name
        student.last_login_at = last_login_at
        self.session.flush()
        return student

    def update_consent_status(
        self,
        student: StudentUser,
        *,
        consent_status: ConsentStatus,
    ) -> StudentUser:
        """Persist the latest derived crisis-intervention consent status."""
        student.consent_status = consent_status
        self.session.flush()
        return student
