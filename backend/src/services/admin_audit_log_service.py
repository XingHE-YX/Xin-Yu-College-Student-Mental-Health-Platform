"""Service layer for administrator audit-log filters and record formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.workflow_enums import AuditActorType
from src.models.admin_user import AdminUser
from src.models.audit_log import AuditLog
from src.models.student_user import StudentUser
from src.repositories.admin_audit_log_repository import AdminAuditLogRepository


@dataclass(frozen=True, slots=True)
class AuditActorOption:
    """One actor filter option shown in the A07 filter bar."""

    actor_type: AuditActorType
    actor_id: int | None
    label: str


@dataclass(frozen=True, slots=True)
class AuditLogListSnapshot:
    """Serialized A07 audit-log payload returned to the route layer."""

    filtered_count: int
    actor_options: list[AuditActorOption]
    action_code_options: list[str]
    target_type_options: list[str]
    records: list[dict[str, Any]]


class AdminAuditLogService:
    """Build filtered audit-log snapshots and stable actor/target labels."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AdminAuditLogRepository(session)

    def list_audit_logs(
        self,
        *,
        actor_type: AuditActorType | None,
        actor_id: int | None,
        action_code: str | None,
        target_type: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> AuditLogListSnapshot:
        """Return the filtered A07 audit-log payload and filter options."""
        created_from = (
            datetime.combine(date_from, time.min) if date_from is not None else None
        )
        created_to_exclusive = (
            datetime.combine(date_to + timedelta(days=1), time.min)
            if date_to is not None
            else None
        )
        logs = self.repository.list_logs(
            actor_type=actor_type,
            actor_id=actor_id,
            action_code=action_code,
            target_type=target_type,
            created_from=created_from,
            created_to_exclusive=created_to_exclusive,
        )
        admin_by_id, student_by_id = self._load_actor_reference_maps(logs)
        records = [
            self._build_record(
                audit_log,
                admin_by_id=admin_by_id,
                student_by_id=student_by_id,
            )
            for audit_log in logs
        ]
        actor_options = self._build_actor_options()
        return AuditLogListSnapshot(
            filtered_count=self.repository.count_logs(
                actor_type=actor_type,
                actor_id=actor_id,
                action_code=action_code,
                target_type=target_type,
                created_from=created_from,
                created_to_exclusive=created_to_exclusive,
            ),
            actor_options=actor_options,
            action_code_options=self.repository.list_distinct_action_codes(),
            target_type_options=self.repository.list_distinct_target_types(),
            records=records,
        )

    def _build_actor_options(self) -> list[AuditActorOption]:
        """Return all distinct audit actor options with stable display labels."""
        actor_refs = self.repository.list_distinct_actor_refs()
        admin_ids = [
            actor_id
            for actor_type, actor_id in actor_refs
            if actor_type is AuditActorType.ADMIN and actor_id is not None
        ]
        student_ids = [
            actor_id
            for actor_type, actor_id in actor_refs
            if actor_type is AuditActorType.STUDENT and actor_id is not None
        ]
        admin_by_id = self._load_admins(admin_ids)
        student_by_id = self._load_students(student_ids)

        options: list[AuditActorOption] = []
        for actor_type, actor_id in actor_refs:
            label = self._resolve_actor_option_label(
                actor_type=actor_type,
                actor_id=actor_id,
                admin_by_id=admin_by_id,
                student_by_id=student_by_id,
            )
            options.append(
                AuditActorOption(
                    actor_type=actor_type,
                    actor_id=actor_id,
                    label=label,
                )
            )
        return options

    def _build_record(
        self,
        audit_log: AuditLog,
        *,
        admin_by_id: dict[int, AdminUser],
        student_by_id: dict[int, StudentUser],
    ) -> dict[str, Any]:
        """Serialize one persisted audit row into the A07 list record shape."""
        return {
            "audit_log_id": audit_log.id,
            "created_at": audit_log.created_at,
            "actor_type": audit_log.actor_type.value,
            "actor_id": audit_log.actor_id,
            "actor_label": self._resolve_actor_label(
                audit_log,
                admin_by_id=admin_by_id,
                student_by_id=student_by_id,
            ),
            "action_code": audit_log.action_code,
            "target_type": audit_log.target_type,
            "target_id": audit_log.target_id,
            "target_label": self._resolve_target_label(audit_log),
            "summary_text": self._build_summary_text(audit_log),
            "metadata_json": audit_log.metadata_json,
            "ip_address": audit_log.ip_address,
        }

    def _load_actor_reference_maps(
        self,
        logs: list[AuditLog],
    ) -> tuple[dict[int, AdminUser], dict[int, StudentUser]]:
        """Load admin and student actors referenced in the current audit result set."""
        admin_ids = [
            actor_id
            for audit_log in logs
            if audit_log.actor_type is AuditActorType.ADMIN
            and (actor_id := audit_log.actor_id) is not None
        ]
        student_ids = [
            actor_id
            for audit_log in logs
            if audit_log.actor_type is AuditActorType.STUDENT
            and (actor_id := audit_log.actor_id) is not None
        ]
        return self._load_admins(admin_ids), self._load_students(student_ids)

    def _load_admins(self, admin_ids: list[int]) -> dict[int, AdminUser]:
        """Return admins keyed by id for the provided id set."""
        if not admin_ids:
            return {}
        statement = select(AdminUser).where(AdminUser.id.in_(set(admin_ids)))
        admins = self.session.scalars(statement).all()
        return {admin.id: admin for admin in admins}

    def _load_students(self, student_ids: list[int]) -> dict[int, StudentUser]:
        """Return students keyed by id for the provided id set."""
        if not student_ids:
            return {}
        statement = select(StudentUser).where(StudentUser.id.in_(set(student_ids)))
        students = self.session.scalars(statement).all()
        return {student.id: student for student in students}

    def _resolve_actor_option_label(
        self,
        *,
        actor_type: AuditActorType,
        actor_id: int | None,
        admin_by_id: dict[int, AdminUser],
        student_by_id: dict[int, StudentUser],
    ) -> str:
        """Return the filter label shown in the A07 actor selectbox."""
        if actor_type is AuditActorType.SYSTEM:
            return "系统"
        if actor_type is AuditActorType.ADMIN:
            if actor_id is None:
                return "管理员"
            admin = admin_by_id.get(actor_id)
            if admin is None:
                return f"管理员 #{actor_id}"
            return f"{admin.display_name} / {admin.username}"
        if actor_id is None:
            return "学生"
        student = student_by_id.get(actor_id)
        if student is None:
            return f"STU-{actor_id:06d}"
        return f"STU-{student.id:06d}"

    def _resolve_actor_label(
        self,
        audit_log: AuditLog,
        *,
        admin_by_id: dict[int, AdminUser],
        student_by_id: dict[int, StudentUser],
    ) -> str:
        """Return the actor label shown on one A07 audit record."""
        return self._resolve_actor_option_label(
            actor_type=audit_log.actor_type,
            actor_id=audit_log.actor_id,
            admin_by_id=admin_by_id,
            student_by_id=student_by_id,
        )

    def _resolve_target_label(self, audit_log: AuditLog) -> str:
        """Return the target label shown on one A07 audit record."""
        target_id = audit_log.target_id
        if audit_log.target_type == "alert_case":
            return f"案例 #{target_id or 0}"
        if audit_log.target_type == "treehole_post":
            return f"帖子 #{target_id or 0}"
        if audit_log.target_type == "student_user":
            return f"STU-{(target_id or 0):06d}"
        if audit_log.target_type == "admin_user":
            return f"管理员 #{target_id or 0}"
        return f"{audit_log.target_type} #{target_id or 0}"

    def _build_summary_text(self, audit_log: AuditLog) -> str:
        """Return one readable audit summary shown on the A07 page."""
        metadata = audit_log.metadata_json or {}
        action_code = audit_log.action_code
        if action_code == "ADMIN_LOGIN_SUCCESS":
            return "管理员登录成功。"
        if action_code == "ADMIN_VIEW_ALERT_CASE_DETAIL":
            return "打开预警案例详情。"
        if action_code == "ADMIN_REVEAL_ALERT_SOURCE_CONTENT":
            return "展开预警来源树洞原文。"
        if action_code == "ADMIN_CONFIRM_ALERT_CASE":
            return f"确认高风险，当前状态为 {metadata.get('queue_status', '--')}。"
        if action_code == "ADMIN_DISMISS_ALERT_CASE":
            return f"标记误报，当前状态为 {metadata.get('queue_status', '--')}。"
        if action_code == "ADMIN_CLOSE_ALERT_CASE":
            return f"结案，当前状态为 {metadata.get('queue_status', '--')}。"
        if action_code == "ADMIN_ADD_INTERVENTION_NOTE":
            return "添加干预记录。"
        if action_code == "SYSTEM_CREATE_SIMULATED_NOTICE_LOG":
            return "系统生成模拟通知日志。"
        if action_code == "ADMIN_REVEAL_POST_CONTENT":
            return "展开帖子完整原文。"
        if action_code == "ADMIN_HIDE_POST":
            return self._build_status_transition_summary(metadata, prefix="隐藏帖子")
        if action_code == "ADMIN_KEEP_POST_HIDDEN":
            return self._build_status_transition_summary(metadata, prefix="保持隐藏")
        if action_code == "ADMIN_RESTORE_POST_VISIBILITY":
            return self._build_status_transition_summary(metadata, prefix="恢复发布")
        if action_code == "ADMIN_VIEW_USER_DETAIL":
            return "打开学生风险档案详情。"
        if action_code == "ADMIN_REVEAL_STUDENT_PHONE":
            return "展开学生完整手机号。"
        return action_code

    def _build_status_transition_summary(
        self,
        metadata: dict[str, Any],
        *,
        prefix: str,
    ) -> str:
        """Return one readable status-transition summary from audit metadata."""
        previous_status = metadata.get("previous_status")
        next_status = metadata.get("next_status")
        if previous_status is None or next_status is None:
            return f"{prefix}。"
        return f"{prefix}：{previous_status} -> {next_status}。"
