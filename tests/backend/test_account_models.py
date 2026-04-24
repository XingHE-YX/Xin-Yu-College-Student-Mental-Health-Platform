"""Tests for the core account ORM models."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from src.constants.account_enums import (
    AdminRoleCode,
    ConsentStatus,
    ConsentType,
    StudentRiskStatus,
)
from src.models import AdminUser, Base, ConsentRecord, StudentUser


def test_core_account_tables_compile_to_mysql_contract() -> None:
    """The account models should compile to the MySQL-oriented schema contract."""
    student_sql = str(CreateTable(StudentUser.__table__).compile(dialect=mysql.dialect()))
    consent_sql = str(CreateTable(ConsentRecord.__table__).compile(dialect=mysql.dialect()))
    admin_sql = str(CreateTable(AdminUser.__table__).compile(dialect=mysql.dialect()))

    assert "BIGINT UNSIGNED NOT NULL AUTO_INCREMENT" in student_sql
    assert "DATETIME(3)" in student_sql
    assert "ENUM('normal','watch','high')" in student_sql
    assert "ENUM('granted','declined','missing')" in student_sql
    assert "CHARSET=utf8mb4" in student_sql
    assert "COLLATE utf8mb4_0900_ai_ci" in student_sql
    assert "FOREIGN KEY(student_id) REFERENCES student_users (id)" in consent_sql
    assert "ENUM('privacy_policy','crisis_intervention_authorization')" in consent_sql
    assert "ENUM('platform_admin','counselor','advisor')" in admin_sql


def test_core_account_tables_create_expected_constraints_and_defaults() -> None:
    """The account models should expose unique keys, foreign keys, and ORM defaults."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            StudentUser.__table__,
            ConsentRecord.__table__,
            AdminUser.__table__,
        ],
    )
    inspector = inspect(engine)

    student_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("student_users")
    }
    admin_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("admin_users")
    }
    consent_foreign_keys = inspector.get_foreign_keys("consent_records")

    assert ("phone_e164",) in student_unique_constraints
    assert ("wechat_openid",) in student_unique_constraints
    assert ("username",) in admin_unique_constraints
    assert consent_foreign_keys[0]["constrained_columns"] == ["student_id"]
    assert consent_foreign_keys[0]["referred_table"] == "student_users"

    with Session(engine) as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-openid-demo",
            display_nickname="安心同学",
            display_avatar_seed="seed-001",
            college_name="心理学院",
            class_name="2026级1班",
        )
        admin = AdminUser(
            username="counselor.demo",
            password_hash="argon2$demo",
            role_code=AdminRoleCode.COUNSELOR,
            display_name="张老师",
        )
        session.add_all([student, admin])
        session.flush()

        consent = ConsentRecord(
            student_id=student.id,
            consent_type=ConsentType.CRISIS_INTERVENTION_AUTHORIZATION,
            consent_version="v1.0",
            granted=True,
            granted_at=student.created_at,
            ip_address="127.0.0.1",
            user_agent="wechat-devtools",
        )
        session.add(consent)
        session.flush()
        session.refresh(student)

        assert student.id is not None
        assert student.risk_status is StudentRiskStatus.NORMAL
        assert student.consent_status is ConsentStatus.MISSING
        assert student.is_demo is False
        assert student.created_at is not None
        assert student.updated_at is not None
        assert admin.id is not None
        assert admin.is_active is True
        assert consent.id is not None
        assert consent.student.id == student.id

    engine.dispose()
