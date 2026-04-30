"""Shared query helpers for hiding or showing seeded demo cases."""

from __future__ import annotations

from sqlalchemy import and_, or_, select

from src.constants.demo_constants import (
    SEEDED_DEMO_AUDIT_IP_ADDRESS,
    SEEDED_DEMO_STUDENT_OPENIDS,
)
from src.constants.workflow_enums import AuditActorType
from src.models.alert_case import AlertCase
from src.models.audit_log import AuditLog
from src.models.student_user import StudentUser
from src.models.treehole_post import TreeholePost


def seeded_student_ids_subquery():
    """Return a subquery selecting all seeded demo-student ids."""
    return select(StudentUser.id).where(
        StudentUser.wechat_openid.in_(SEEDED_DEMO_STUDENT_OPENIDS)
    )


def exclude_seeded_students_clause(student_id_column):
    """Return a SQLAlchemy clause excluding rows owned by seeded demo students."""
    return ~student_id_column.in_(seeded_student_ids_subquery())


def exclude_seeded_audit_logs_clause():
    """Return a SQLAlchemy clause excluding audit logs belonging to seeded demos."""
    seeded_student_ids = seeded_student_ids_subquery()
    seeded_post_ids = select(TreeholePost.id).where(
        TreeholePost.student_id.in_(seeded_student_ids)
    )
    seeded_alert_ids = select(AlertCase.id).where(
        AlertCase.student_id.in_(seeded_student_ids)
    )

    return ~or_(
        and_(
            AuditLog.ip_address.is_not(None),
            AuditLog.ip_address == SEEDED_DEMO_AUDIT_IP_ADDRESS,
        ),
        and_(
            AuditLog.actor_type == AuditActorType.STUDENT,
            AuditLog.actor_id.is_not(None),
            AuditLog.actor_id.in_(seeded_student_ids),
        ),
        and_(
            AuditLog.target_type == "student_user",
            AuditLog.target_id.is_not(None),
            AuditLog.target_id.in_(seeded_student_ids),
        ),
        and_(
            AuditLog.target_type == "treehole_post",
            AuditLog.target_id.is_not(None),
            AuditLog.target_id.in_(seeded_post_ids),
        ),
        and_(
            AuditLog.target_type == "alert_case",
            AuditLog.target_id.is_not(None),
            AuditLog.target_id.in_(seeded_alert_ids),
        ),
    )
