"""Service layer for administrator alert queue and detail views."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from src.constants.workflow_enums import (
    AlertQueueStatus,
    AuditActorType,
    ReviewPriority,
)
from src.models.alert_case import AlertCase
from src.models.audit_log import AuditLog
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.repositories.admin_alert_repository import AdminAlertRepository

QUEUE_STATUS_DISPLAY_ORDER = (
    AlertQueueStatus.PENDING_REVIEW,
    AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
    AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
    AlertQueueStatus.CLOSED,
)
QUEUE_STATUS_LABELS = {
    AlertQueueStatus.PENDING_REVIEW: "待复核",
    AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION: "已确认",
    AlertQueueStatus.DISMISSED_FALSE_POSITIVE: "已忽略",
    AlertQueueStatus.CLOSED: "已结案",
}
SOURCE_TYPE_LABELS = {
    "treehole": "树洞内容",
    "assessment": "量表预警",
    "history": "历史复查",
}
PRIORITY_LABELS = {
    ReviewPriority.HIGHEST: "最高优先级",
    ReviewPriority.URGENT: "紧急",
    ReviewPriority.NORMAL: "常规",
}


class AdminAlertServiceError(ValueError):
    """Base error raised when administrator alert data cannot be loaded."""


class AlertCaseNotFoundError(AdminAlertServiceError):
    """Raised when one requested alert case does not exist."""


class AlertSourceContentUnavailableError(AdminAlertServiceError):
    """Raised when one alert case has no revealable treehole raw content."""


@dataclass(frozen=True, slots=True)
class AlertQueueStatusCount:
    """One queue-status count bucket used by the A03 filter controls."""

    queue_status: AlertQueueStatus
    count: int


@dataclass(frozen=True, slots=True)
class AlertQueueListItem:
    """Compact alert row shown in the left-side A03 case list."""

    alert_id: int
    created_at: Any
    queue_status: AlertQueueStatus
    review_priority: ReviewPriority
    case_level: str
    source_type: str
    source_label: str
    source_preview: str
    student_label: str
    masked_phone: str
    college_name: str
    class_name: str
    risk_status: str
    reviewer_display_name: str | None
    reviewed_at: Any


@dataclass(frozen=True, slots=True)
class AlertQueueSnapshot:
    """Serialized queue data returned to the Streamlit A03 master list."""

    applied_queue_status: AlertQueueStatus | None
    status_counts: list[AlertQueueStatusCount]
    items: list[AlertQueueListItem]


class AdminAlertService:
    """Build alert queue snapshots and audited alert detail payloads."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AdminAlertRepository(session)

    def list_alert_queue(
        self,
        *,
        queue_status: AlertQueueStatus | None,
    ) -> AlertQueueSnapshot:
        """Return the filtered alert queue and all status counts for A03."""
        counts_by_status = self.repository.count_alert_cases_by_status()
        items = [
            self._build_list_item(alert_case)
            for alert_case in self.repository.list_alert_cases(queue_status=queue_status)
        ]
        return AlertQueueSnapshot(
            applied_queue_status=queue_status,
            status_counts=[
                AlertQueueStatusCount(
                    queue_status=status,
                    count=counts_by_status.get(status, 0),
                )
                for status in QUEUE_STATUS_DISPLAY_ORDER
            ],
            items=items,
        )

    def get_alert_detail(
        self,
        *,
        alert_case_id: int,
        admin_user_id: int,
        ip_address: str | None,
    ) -> dict[str, Any]:
        """Return one alert detail payload and audit the sensitive detail view."""
        alert_case = self._load_alert_case(alert_case_id)
        alert_payload = self._build_detail_payload(alert_case, include_full_content=False)
        self._append_audit_log(
            admin_user_id=admin_user_id,
            action_code="ADMIN_VIEW_ALERT_CASE_DETAIL",
            target_type="alert_case",
            target_id=alert_case.id,
            ip_address=ip_address,
            metadata_json={
                "queue_status": alert_case.queue_status.value,
                "source_type": alert_case.source_type.value,
                "review_priority": alert_case.review_priority.value,
            },
        )
        self.session.commit()
        return alert_payload

    def reveal_treehole_content(
        self,
        *,
        alert_case_id: int,
        admin_user_id: int,
        ip_address: str | None,
    ) -> dict[str, Any]:
        """Return the raw treehole content for one alert case and audit the reveal."""
        alert_case = self._load_alert_case(alert_case_id)
        source_post = alert_case.source_post
        if source_post is None or not source_post.content_raw.strip():
            raise AlertSourceContentUnavailableError(
                f"alert case '{alert_case_id}' has no revealable treehole content"
            )

        self._append_audit_log(
            admin_user_id=admin_user_id,
            action_code="ADMIN_REVEAL_ALERT_SOURCE_CONTENT",
            target_type="treehole_post",
            target_id=source_post.id,
            ip_address=ip_address,
            metadata_json={
                "alert_case_id": alert_case.id,
                "queue_status": alert_case.queue_status.value,
            },
        )
        self.session.commit()
        return {
            "alert_id": alert_case.id,
            "source_type": alert_case.source_type.value,
            "full_content": source_post.content_raw,
        }

    def _build_list_item(self, alert_case: AlertCase) -> AlertQueueListItem:
        """Serialize one alert case into the compact queue-list row shape."""
        student = alert_case.student
        if student is None:
            raise AlertCaseNotFoundError(
                f"alert case '{alert_case.id}' is missing its student relation"
            )

        source_label = self._resolve_source_label(alert_case)
        source_preview = self._resolve_source_preview(alert_case)
        reviewer_display_name = (
            alert_case.reviewer.display_name if alert_case.reviewer is not None else None
        )
        return AlertQueueListItem(
            alert_id=alert_case.id,
            created_at=alert_case.created_at,
            queue_status=alert_case.queue_status,
            review_priority=alert_case.review_priority,
            case_level=alert_case.case_level.value,
            source_type=alert_case.source_type.value,
            source_label=source_label,
            source_preview=source_preview,
            student_label=self._build_student_label(student.id),
            masked_phone=self._mask_phone(student.phone_e164),
            college_name=student.college_name,
            class_name=student.class_name,
            risk_status=student.risk_status.value,
            reviewer_display_name=reviewer_display_name,
            reviewed_at=alert_case.reviewed_at,
        )

    def _build_detail_payload(
        self,
        alert_case: AlertCase,
        *,
        include_full_content: bool,
    ) -> dict[str, Any]:
        """Serialize one alert case into the A04 detail payload shape."""
        student = alert_case.student
        if student is None:
            raise AlertCaseNotFoundError(
                f"alert case '{alert_case.id}' is missing its student relation"
            )

        return {
            "alert_id": alert_case.id,
            "created_at": alert_case.created_at,
            "queue_status": alert_case.queue_status.value,
            "queue_status_label": QUEUE_STATUS_LABELS[alert_case.queue_status],
            "review_priority": alert_case.review_priority.value,
            "review_priority_label": PRIORITY_LABELS[alert_case.review_priority],
            "case_level": alert_case.case_level.value,
            "source_type": alert_case.source_type.value,
            "source_type_label": SOURCE_TYPE_LABELS.get(
                alert_case.source_type.value,
                alert_case.source_type.value,
            ),
            "ai_reason_text": alert_case.ai_reason_text,
            "review_note": alert_case.review_note,
            "simulated_notice_log": alert_case.simulated_notice_log,
            "reviewed_at": alert_case.reviewed_at,
            "reviewer_display_name": (
                alert_case.reviewer.display_name
                if alert_case.reviewer is not None
                else None
            ),
            "student": {
                "student_label": self._build_student_label(student.id),
                "masked_phone": self._mask_phone(student.phone_e164),
                "college_name": student.college_name,
                "class_name": student.class_name,
                "risk_status": student.risk_status.value,
                "consent_status": student.consent_status.value,
            },
            "source": self._build_source_context(
                alert_case,
                include_full_content=include_full_content,
            ),
            "history": self._build_history_context(alert_case),
            "intervention_logs": self._build_intervention_logs(alert_case),
            "action_permissions": self._build_action_permissions(alert_case),
        }

    def _build_source_context(
        self,
        alert_case: AlertCase,
        *,
        include_full_content: bool,
    ) -> dict[str, Any]:
        """Return the source-specific detail block for one alert case."""
        if alert_case.source_type.value == "treehole":
            post = alert_case.source_post
            if post is None:
                raise AlertCaseNotFoundError(
                    f"treehole alert case '{alert_case.id}' is missing its source post"
                )

            analysis_record = max(
                post.ai_analysis_records,
                key=lambda record: (record.created_at, record.id),
                default=None,
            )
            return {
                "kind": "treehole",
                "anonymous_name": post.anonymous_name,
                "created_at": post.created_at,
                "publish_status": post.publish_status.value,
                "risk_level": post.risk_level.value,
                "masked_content": (
                    post.content_masked
                    or "该树洞内容已被系统拦截，默认仅展示脱敏上下文。"
                ),
                "full_content_available": bool(post.content_raw.strip()),
                "full_content": post.content_raw if include_full_content else None,
                "ai_analysis": self._serialize_ai_analysis_record(analysis_record),
            }

        submission = alert_case.source_submission
        if submission is None:
            raise AlertCaseNotFoundError(
                f"assessment alert case '{alert_case.id}' is missing its source submission"
            )

        template = submission.template
        snapshot = submission.scoring_snapshot_json or {}
        questionnaire_code = (
            template.code if template is not None else str(snapshot.get("questionnaire_code", "--"))
        )
        questionnaire_name = (
            template.name if template is not None else questionnaire_code
        )
        return {
            "kind": "assessment",
            "questionnaire_code": questionnaire_code,
            "questionnaire_name": questionnaire_name,
            "submitted_at": submission.submitted_at,
            "raw_score": submission.raw_score,
            "standardized_score": submission.standardized_score,
            "risk_level": submission.risk_level.value,
            "hard_trigger_hit": submission.hard_trigger_hit,
            "hard_trigger_matches": snapshot.get("hard_trigger_matches", []),
            "result_summary": self._build_assessment_result_summary(submission),
        }

    def _build_history_context(self, alert_case: AlertCase) -> dict[str, Any]:
        """Return latest assessment summaries and historical high-risk flags."""
        student = alert_case.student
        assert student is not None

        current_submission_id = (
            alert_case.source_submission.id
            if alert_case.source_submission is not None
            else None
        )
        current_post_id = alert_case.source_post.id if alert_case.source_post is not None else None

        history_flags: list[dict[str, str]] = []
        if student.risk_status.value == "high":
            history_flags.append(
                {
                    "code": "CURRENT_HIGH_RISK_STATUS",
                    "label": "当前学生档案仍处于高风险状态。",
                }
            )
        if self.repository.has_other_high_risk_submission(
            student_id=student.id,
            exclude_submission_id=current_submission_id,
        ):
            history_flags.append(
                {
                    "code": "PRIOR_HIGH_RISK_ASSESSMENT",
                    "label": "存在其他历史高风险量表记录。",
                }
            )
        if self.repository.has_other_high_risk_treehole_post(
            student_id=student.id,
            exclude_post_id=current_post_id,
        ):
            history_flags.append(
                {
                    "code": "PRIOR_HIGH_RISK_TREEHOLE",
                    "label": "存在其他历史高风险树洞记录。",
                }
            )

        latest_questionnaires: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for submission in self.repository.list_student_submissions(student_id=student.id):
            template = submission.template
            questionnaire_code = (
                template.code
                if template is not None
                else str(
                    (submission.scoring_snapshot_json or {}).get(
                        "questionnaire_code",
                        "--",
                    )
                )
            )
            if questionnaire_code in seen_codes:
                continue
            seen_codes.add(questionnaire_code)
            latest_questionnaires.append(
                {
                    "questionnaire_code": questionnaire_code,
                    "questionnaire_name": (
                        template.name if template is not None else questionnaire_code
                    ),
                    "submitted_at": submission.submitted_at,
                    "risk_level": submission.risk_level.value,
                    "raw_score": submission.raw_score,
                    "standardized_score": submission.standardized_score,
                    "hard_trigger_hit": submission.hard_trigger_hit,
                    "is_current_source": submission.id == current_submission_id,
                }
            )
            if len(latest_questionnaires) >= 5:
                break

        return {
            "has_history_high_risk": bool(history_flags),
            "history_flags": history_flags,
            "latest_questionnaires": latest_questionnaires,
        }

    def _build_intervention_logs(self, alert_case: AlertCase) -> list[dict[str, Any]]:
        """Return the intervention timeline newest-first for the current alert case."""
        ordered_logs = sorted(
            alert_case.intervention_logs,
            key=lambda log: (log.created_at, log.id),
            reverse=True,
        )
        return [
            {
                "intervention_log_id": log.id,
                "created_at": log.created_at,
                "action_type": log.action_type.value,
                "action_note": log.action_note,
                "admin_display_name": log.admin_user.display_name,
                "admin_role_code": log.admin_user.role_code.value,
            }
            for log in ordered_logs
        ]

    def _build_action_permissions(self, alert_case: AlertCase) -> dict[str, bool]:
        """Return which manual actions should be shown for the current workflow state."""
        is_pending = alert_case.queue_status is AlertQueueStatus.PENDING_REVIEW
        can_close = alert_case.queue_status in {
            AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
            AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
        }
        can_add_note = alert_case.queue_status in {
            AlertQueueStatus.PENDING_REVIEW,
            AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
            AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
        }
        return {
            "can_confirm": is_pending,
            "can_dismiss": is_pending,
            "can_close": can_close,
            "can_add_note": can_add_note,
        }

    def _serialize_ai_analysis_record(self, analysis_record) -> dict[str, Any] | None:
        """Return the treehole AI analysis block when one analysis record exists."""
        if analysis_record is None:
            return None
        risk_score = analysis_record.parsed_risk_score
        return {
            "parsed_risk_level": analysis_record.parsed_risk_level.value,
            "parsed_risk_score": self._serialize_decimal(risk_score),
            "emotion_tags": list(analysis_record.emotion_tags_json),
            "trigger_phrases": list(analysis_record.trigger_phrases_json),
            "reason_text": analysis_record.reason_text,
            "recommended_action": analysis_record.recommended_action.value,
            "fallback_used": analysis_record.fallback_used,
        }

    def _build_assessment_result_summary(
        self,
        submission: QuestionnaireSubmission,
    ) -> str:
        """Build one readable score summary for the assessment detail block."""
        if submission.standardized_score is None:
            return f"原始分 {submission.raw_score}"
        return f"原始分 {submission.raw_score}，标准分 {submission.standardized_score}"

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
        """Persist one admin audit event related to alert detail or reveal viewing."""
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

    def _load_alert_case(self, alert_case_id: int) -> AlertCase:
        """Load one alert case or raise a business error."""
        alert_case = self.repository.get_alert_case_detail(alert_case_id)
        if alert_case is None:
            raise AlertCaseNotFoundError(f"alert case '{alert_case_id}' does not exist")
        return alert_case

    def _resolve_source_label(self, alert_case: AlertCase) -> str:
        """Return the list-page label for the alert source."""
        if alert_case.source_type.value == "treehole":
            return "树洞高风险内容"
        submission = alert_case.source_submission
        template = submission.template if submission is not None else None
        if template is None:
            return "量表预警"
        return f"{template.code} · {template.name}"

    def _resolve_source_preview(self, alert_case: AlertCase) -> str:
        """Return the compact preview shown inside one queue list card."""
        if alert_case.source_type.value == "treehole":
            source_post = alert_case.source_post
            if source_post is None:
                return "树洞原始来源缺失。"
            return self._truncate_text(
                source_post.content_masked
                or "该高风险树洞内容已被系统拦截，默认不在列表中直接展示原文。"
            )
        return self._truncate_text(
            alert_case.ai_reason_text
            or "该量表结果已达到高风险阈值，请在详情页查看具体触发原因。"
        )

    def _build_student_label(self, student_id: int) -> str:
        """Return one stable masked student identifier for admin list/detail views."""
        return f"STU-{student_id:06d}"

    def _mask_phone(self, phone_number: str) -> str:
        """Return a lightly masked phone string for admin list/detail views."""
        if len(phone_number) <= 6:
            return phone_number[:1] + "***"
        return f"{phone_number[:5]}****{phone_number[-2:]}"

    def _serialize_decimal(self, value: Decimal) -> float:
        """Convert one Decimal risk score into a JSON-friendly float."""
        return float(value)

    def _truncate_text(self, text: str, *, max_length: int = 68) -> str:
        """Clamp a list-page preview string without breaking the admin layout."""
        normalized = " ".join(text.split())
        if len(normalized) <= max_length:
            return normalized
        return f"{normalized[: max_length - 1]}…"
