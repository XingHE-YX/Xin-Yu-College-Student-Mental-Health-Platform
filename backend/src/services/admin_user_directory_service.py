"""Service layer for administrator user-directory views and sensitive reveal actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.constants.account_enums import StudentRiskStatus
from src.constants.workflow_enums import AlertQueueStatus, AuditActorType, FocusListStatus
from src.models.audit_log import AuditLog
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.models.student_user import StudentUser
from src.repositories.admin_user_directory_repository import AdminUserDirectoryRepository

RISK_STATUS_DISPLAY_ORDER = (
    StudentRiskStatus.HIGH,
    StudentRiskStatus.WATCH,
    StudentRiskStatus.NORMAL,
)


class AdminUserDirectoryServiceError(ValueError):
    """Base error raised when administrator user-directory data cannot be loaded."""


class AdminStudentNotFoundError(AdminUserDirectoryServiceError):
    """Raised when one requested student does not exist."""


@dataclass(frozen=True, slots=True)
class StudentRiskStatusCount:
    """One risk-status count bucket used by the A06 filter controls."""

    risk_status: StudentRiskStatus
    count: int


@dataclass(frozen=True, slots=True)
class AdminStudentListItem:
    """Compact user-directory row shown in the left-side A06 list."""

    student_id: int
    student_label: str
    masked_phone: str
    college_name: str
    class_name: str
    risk_status: str
    consent_status: str
    active_focus_count: int
    open_alert_count: int
    last_login_at: Any
    updated_at: Any


@dataclass(frozen=True, slots=True)
class AdminStudentListSnapshot:
    """Serialized A06 list payload returned to the route layer."""

    applied_risk_status: StudentRiskStatus | None
    status_counts: list[StudentRiskStatusCount]
    items: list[AdminStudentListItem]


class AdminUserDirectoryService:
    """Build masked student-directory snapshots and audited sensitive user actions."""

    def __init__(self, session: Session, *, show_seeded_cases: bool = True) -> None:
        self.session = session
        self.repository = AdminUserDirectoryRepository(session)
        self.show_seeded_cases = show_seeded_cases

    def list_students(
        self,
        *,
        risk_status: StudentRiskStatus | None,
    ) -> AdminStudentListSnapshot:
        """Return the filtered A06 user list and grouped risk-status counts."""
        counts_by_status = self.repository.count_students_by_risk_status(
            show_seeded_cases=self.show_seeded_cases
        )
        focus_counts = self.repository.count_active_focus_entries_by_student(
            show_seeded_cases=self.show_seeded_cases
        )
        open_alert_counts = self.repository.count_open_alert_cases_by_student(
            show_seeded_cases=self.show_seeded_cases
        )
        items = [
            self._build_list_item(
                student,
                active_focus_count=focus_counts.get(student.id, 0),
                open_alert_count=open_alert_counts.get(student.id, 0),
            )
            for student in self.repository.list_students(
                risk_status=risk_status,
                show_seeded_cases=self.show_seeded_cases,
            )
        ]
        return AdminStudentListSnapshot(
            applied_risk_status=risk_status,
            status_counts=[
                StudentRiskStatusCount(
                    risk_status=status,
                    count=counts_by_status.get(status, 0),
                )
                for status in RISK_STATUS_DISPLAY_ORDER
            ],
            items=items,
        )

    def get_student_detail(
        self,
        *,
        student_id: int,
        admin_user_id: int,
        ip_address: str | None,
    ) -> dict[str, Any]:
        """Return one A06 student detail payload and audit the sensitive detail view."""
        student = self._load_student(student_id)
        detail_payload = self._build_student_detail_payload(student, include_full_phone=False)
        self._append_audit_log(
            admin_user_id=admin_user_id,
            action_code="ADMIN_VIEW_USER_DETAIL",
            target_type="student_user",
            target_id=student.id,
            ip_address=ip_address,
            metadata_json={
                "risk_status": student.risk_status.value,
                "consent_status": student.consent_status.value,
            },
        )
        self.session.commit()
        return detail_payload

    def reveal_student_phone(
        self,
        *,
        student_id: int,
        admin_user_id: int,
        ip_address: str | None,
    ) -> dict[str, Any]:
        """Return the student's full phone number and audit the explicit reveal."""
        student = self._load_student(student_id)
        self._append_audit_log(
            admin_user_id=admin_user_id,
            action_code="ADMIN_REVEAL_STUDENT_PHONE",
            target_type="student_user",
            target_id=student.id,
            ip_address=ip_address,
            metadata_json={
                "risk_status": student.risk_status.value,
            },
        )
        self.session.commit()
        return {
            "student_id": student.id,
            "full_phone": student.phone_e164,
        }

    def _build_list_item(
        self,
        student: StudentUser,
        *,
        active_focus_count: int,
        open_alert_count: int,
    ) -> AdminStudentListItem:
        """Serialize one student into the compact A06 list-row shape."""
        return AdminStudentListItem(
            student_id=student.id,
            student_label=self._build_student_label(student.id),
            masked_phone=self._mask_phone(student.phone_e164),
            college_name=student.college_name,
            class_name=student.class_name,
            risk_status=student.risk_status.value,
            consent_status=student.consent_status.value,
            active_focus_count=active_focus_count,
            open_alert_count=open_alert_count,
            last_login_at=student.last_login_at,
            updated_at=student.updated_at,
        )

    def _build_student_detail_payload(
        self,
        student: StudentUser,
        *,
        include_full_phone: bool,
    ) -> dict[str, Any]:
        """Serialize one student into the A06 detail payload shape."""
        latest_questionnaires = self._build_latest_questionnaire_summary(student)
        latest_posts = self._build_latest_post_summary(student)
        active_focus_entries = [
            {
                "focus_entry_id": entry.id,
                "reason_code": entry.reason_code,
                "status": entry.status.value,
                "created_at": entry.created_at,
            }
            for entry in sorted(
                student.focus_list_entries,
                key=lambda entry: (entry.created_at, entry.id),
                reverse=True,
            )[:5]
        ]
        recent_alert_cases = [
            {
                "alert_id": alert_case.id,
                "queue_status": alert_case.queue_status.value,
                "review_priority": alert_case.review_priority.value,
                "source_type": alert_case.source_type.value,
                "created_at": alert_case.created_at,
            }
            for alert_case in sorted(
                student.alert_cases,
                key=lambda alert_case: (alert_case.created_at, alert_case.id),
                reverse=True,
            )[:5]
        ]

        return {
            "student_id": student.id,
            "student_label": self._build_student_label(student.id),
            "masked_phone": self._mask_phone(student.phone_e164),
            "full_phone": student.phone_e164 if include_full_phone else None,
            "risk_status": student.risk_status.value,
            "consent_status": student.consent_status.value,
            "is_demo": student.is_demo,
            "college_name": student.college_name,
            "class_name": student.class_name,
            "last_login_at": student.last_login_at,
            "created_at": student.created_at,
            "updated_at": student.updated_at,
            "summary": {
                "active_focus_count": sum(
                    1
                    for entry in student.focus_list_entries
                    if entry.status is FocusListStatus.ACTIVE
                ),
                "open_alert_count": sum(
                    1
                    for alert_case in student.alert_cases
                    if alert_case.queue_status
                    in {
                        AlertQueueStatus.PENDING_REVIEW,
                        AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
                    }
                ),
                "treehole_post_count": len(student.treehole_posts),
            },
            "latest_questionnaires": latest_questionnaires,
            "latest_posts": latest_posts,
            "focus_entries": active_focus_entries,
            "recent_alert_cases": recent_alert_cases,
        }

    def _build_latest_questionnaire_summary(
        self,
        student: StudentUser,
    ) -> list[dict[str, Any]]:
        """Return the latest questionnaire summary per code for the A06 detail pane."""
        ordered_submissions = sorted(
            student.questionnaire_submissions,
            key=lambda submission: (submission.submitted_at, submission.id),
            reverse=True,
        )
        latest_by_code: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for submission in ordered_submissions:
            questionnaire_code = self._resolve_questionnaire_code(submission)
            if questionnaire_code in seen_codes:
                continue
            seen_codes.add(questionnaire_code)
            latest_by_code.append(
                {
                    "questionnaire_code": questionnaire_code,
                    "questionnaire_name": (
                        submission.template.name
                        if submission.template is not None
                        else questionnaire_code
                    ),
                    "submitted_at": submission.submitted_at,
                    "risk_level": submission.risk_level.value,
                    "raw_score": submission.raw_score,
                    "standardized_score": submission.standardized_score,
                    "hard_trigger_hit": submission.hard_trigger_hit,
                }
            )
            if len(latest_by_code) >= 5:
                break
        return latest_by_code

    def _build_latest_post_summary(
        self,
        student: StudentUser,
    ) -> list[dict[str, Any]]:
        """Return recent treehole post summaries for the A06 detail pane."""
        ordered_posts = sorted(
            student.treehole_posts,
            key=lambda post: (
                post.created_at,
                post.id,
            ),
            reverse=True,
        )
        return [
            {
                "post_id": post.id,
                "publish_status": post.publish_status.value,
                "risk_level": post.risk_level.value,
                "created_at": post.created_at,
                "published_at": post.published_at,
            }
            for post in ordered_posts[:5]
        ]

    def _resolve_questionnaire_code(
        self,
        submission: QuestionnaireSubmission,
    ) -> str:
        """Return the stable questionnaire code for one submission."""
        if submission.template is not None:
            return submission.template.code
        snapshot = submission.scoring_snapshot_json or {}
        return str(snapshot.get("questionnaire_code", "--"))

    def _append_audit_log(
        self,
        *,
        admin_user_id: int,
        action_code: str,
        target_type: str,
        target_id: int,
        ip_address: str | None,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        """Persist one admin audit event related to A06 detail or phone reveal."""
        self.repository.add_audit_log(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                actor_id=admin_user_id,
                action_code=action_code,
                target_type=target_type,
                target_id=target_id,
                metadata_json=metadata_json,
                ip_address=ip_address,
            )
        )

    def _load_student(self, student_id: int) -> StudentUser:
        """Load one student with detail relationships or raise a business error."""
        student = self.repository.get_student_detail(
            student_id,
            show_seeded_cases=self.show_seeded_cases,
        )
        if student is None:
            raise AdminStudentNotFoundError(f"student '{student_id}' does not exist")
        return student

    def _build_student_label(self, student_id: int) -> str:
        """Return one stable masked student identifier used across admin pages."""
        return f"STU-{student_id:06d}"

    def _mask_phone(self, phone_number: str) -> str:
        """Return a lightly masked phone string for admin list/detail views."""
        if len(phone_number) <= 6:
            return phone_number[:1] + "***"
        return f"{phone_number[:5]}****{phone_number[-2:]}"
