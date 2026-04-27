"""Manual review workflow for alert cases and intervention timelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.constants.workflow_enums import (
    AlertQueueStatus,
    AuditActorType,
    InterventionActionType,
)
from src.models.admin_user import AdminUser
from src.models.alert_case import AlertCase
from src.models.audit_log import AuditLog
from src.models.base import utc_now
from src.models.intervention_log import InterventionLog
from src.repositories.review_workflow_repository import ReviewWorkflowRepository

SIMULATED_NOTICE_PREFIX = "[SIMULATED] Notification recorded for counselor follow-up."


class AlertReviewServiceError(ValueError):
    """Base error raised when manual alert review cannot proceed."""


class AlertCaseNotFoundError(AlertReviewServiceError):
    """Raised when one target alert case does not exist."""


class AdminUserNotFoundError(AlertReviewServiceError):
    """Raised when the acting administrator does not exist."""


class AdminUserInactiveError(AlertReviewServiceError):
    """Raised when an inactive administrator attempts a review action."""


class InvalidAlertCaseTransitionError(AlertReviewServiceError):
    """Raised when one alert case cannot move to the requested next state."""


@dataclass(frozen=True, slots=True)
class AlertReviewActionResult:
    """Result of one manual review action."""

    alert_case: AlertCase


class AlertReviewService:
    """Handle confirm, dismiss, close, and note actions on alert cases."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ReviewWorkflowRepository(session)

    def confirm_high_risk(
        self,
        *,
        alert_case_id: int,
        admin_user_id: int,
        review_note: str,
        intervention_note: str,
        ip_address: str | None = None,
    ) -> AlertReviewActionResult:
        """Confirm one pending alert case as high risk and log simulated contact."""
        alert_case = self._load_alert_case(alert_case_id)
        admin = self._load_admin(admin_user_id)
        self._require_status(
            alert_case,
            allowed_statuses={AlertQueueStatus.PENDING_REVIEW},
            action_name="confirm",
        )

        normalized_review_note = self._normalize_required_text(
            review_note,
            field_name="review_note",
        )
        normalized_intervention_note = self._normalize_required_text(
            intervention_note,
            field_name="intervention_note",
        )
        simulated_notice_log = self._build_simulated_notice_log(
            intervention_note=normalized_intervention_note
        )

        alert_case.queue_status = AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION
        alert_case.review_note = normalized_review_note
        alert_case.reviewed_by = admin.id
        alert_case.reviewed_at = utc_now()
        alert_case.simulated_notice_log = simulated_notice_log

        self.repository.add_intervention_log(
            InterventionLog(
                alert_case_id=alert_case.id,
                admin_user_id=admin.id,
                action_type=InterventionActionType.CONFIRM_HIGH_RISK,
                action_note=normalized_review_note,
            )
        )
        self.repository.add_intervention_log(
            InterventionLog(
                alert_case_id=alert_case.id,
                admin_user_id=admin.id,
                action_type=InterventionActionType.SIMULATE_CONTACT,
                action_note=normalized_intervention_note,
            )
        )
        self._append_admin_audit_log(
            admin=admin,
            action_code="ADMIN_CONFIRM_ALERT_CASE",
            alert_case=alert_case,
            ip_address=ip_address,
            metadata_json={
                "queue_status": alert_case.queue_status.value,
            },
        )
        self._append_system_audit_log(
            action_code="SYSTEM_CREATE_SIMULATED_NOTICE_LOG",
            alert_case=alert_case,
            metadata_json={
                "queue_status": alert_case.queue_status.value,
                "simulated_notice_log": simulated_notice_log,
                "admin_user_id": admin.id,
            },
        )
        self.session.commit()
        self.session.refresh(alert_case)
        return AlertReviewActionResult(alert_case=alert_case)

    def dismiss_false_positive(
        self,
        *,
        alert_case_id: int,
        admin_user_id: int,
        review_note: str,
        ip_address: str | None = None,
    ) -> AlertReviewActionResult:
        """Dismiss one pending alert case as a false positive."""
        alert_case = self._load_alert_case(alert_case_id)
        admin = self._load_admin(admin_user_id)
        self._require_status(
            alert_case,
            allowed_statuses={AlertQueueStatus.PENDING_REVIEW},
            action_name="dismiss",
        )

        normalized_review_note = self._normalize_required_text(
            review_note,
            field_name="review_note",
        )
        alert_case.queue_status = AlertQueueStatus.DISMISSED_FALSE_POSITIVE
        alert_case.review_note = normalized_review_note
        alert_case.reviewed_by = admin.id
        alert_case.reviewed_at = utc_now()

        self.repository.add_intervention_log(
            InterventionLog(
                alert_case_id=alert_case.id,
                admin_user_id=admin.id,
                action_type=InterventionActionType.DISMISS_FALSE_POSITIVE,
                action_note=normalized_review_note,
            )
        )
        self._append_admin_audit_log(
            admin=admin,
            action_code="ADMIN_DISMISS_ALERT_CASE",
            alert_case=alert_case,
            ip_address=ip_address,
            metadata_json={
                "queue_status": alert_case.queue_status.value,
            },
        )
        self.session.commit()
        self.session.refresh(alert_case)
        return AlertReviewActionResult(alert_case=alert_case)

    def close_case(
        self,
        *,
        alert_case_id: int,
        admin_user_id: int,
        action_note: str,
        ip_address: str | None = None,
    ) -> AlertReviewActionResult:
        """Close one reviewed alert case and append a closure log."""
        alert_case = self._load_alert_case(alert_case_id)
        admin = self._load_admin(admin_user_id)
        self._require_status(
            alert_case,
            allowed_statuses={
                AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
                AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
            },
            action_name="close",
        )

        normalized_action_note = self._normalize_required_text(
            action_note,
            field_name="action_note",
        )
        alert_case.queue_status = AlertQueueStatus.CLOSED

        self.repository.add_intervention_log(
            InterventionLog(
                alert_case_id=alert_case.id,
                admin_user_id=admin.id,
                action_type=InterventionActionType.CLOSE_CASE,
                action_note=normalized_action_note,
            )
        )
        self._append_admin_audit_log(
            admin=admin,
            action_code="ADMIN_CLOSE_ALERT_CASE",
            alert_case=alert_case,
            ip_address=ip_address,
            metadata_json={
                "queue_status": alert_case.queue_status.value,
            },
        )
        self.session.commit()
        self.session.refresh(alert_case)
        return AlertReviewActionResult(alert_case=alert_case)

    def add_intervention_note(
        self,
        *,
        alert_case_id: int,
        admin_user_id: int,
        action_note: str,
        ip_address: str | None = None,
    ) -> AlertReviewActionResult:
        """Append one intervention note without changing the alert-case status."""
        alert_case = self._load_alert_case(alert_case_id)
        admin = self._load_admin(admin_user_id)
        self._require_status(
            alert_case,
            allowed_statuses={
                AlertQueueStatus.PENDING_REVIEW,
                AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
                AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
            },
            action_name="add_note",
        )

        normalized_action_note = self._normalize_required_text(
            action_note,
            field_name="action_note",
        )
        self.repository.add_intervention_log(
            InterventionLog(
                alert_case_id=alert_case.id,
                admin_user_id=admin.id,
                action_type=InterventionActionType.ADD_NOTE,
                action_note=normalized_action_note,
            )
        )
        self._append_admin_audit_log(
            admin=admin,
            action_code="ADMIN_ADD_INTERVENTION_NOTE",
            alert_case=alert_case,
            ip_address=ip_address,
            metadata_json={
                "queue_status": alert_case.queue_status.value,
            },
        )
        self.session.commit()
        self.session.refresh(alert_case)
        return AlertReviewActionResult(alert_case=alert_case)

    def _load_alert_case(self, alert_case_id: int) -> AlertCase:
        """Load one alert case or raise a business error."""
        alert_case = self.repository.get_alert_case_by_id(alert_case_id)
        if alert_case is None:
            raise AlertCaseNotFoundError(f"alert case '{alert_case_id}' does not exist")
        return alert_case

    def _load_admin(self, admin_user_id: int) -> AdminUser:
        """Load one active administrator or raise a business error."""
        admin = self.session.get(AdminUser, admin_user_id)
        if admin is None:
            raise AdminUserNotFoundError(f"admin user '{admin_user_id}' does not exist")
        if not admin.is_active:
            raise AdminUserInactiveError(
                f"admin user '{admin_user_id}' is inactive and cannot review alerts"
            )
        return admin

    def _require_status(
        self,
        alert_case: AlertCase,
        *,
        allowed_statuses: set[AlertQueueStatus],
        action_name: str,
    ) -> None:
        """Ensure one alert case is currently eligible for the requested action."""
        if alert_case.queue_status not in allowed_statuses:
            allowed = ", ".join(status.value for status in sorted(allowed_statuses))
            raise InvalidAlertCaseTransitionError(
                f"cannot {action_name} alert case {alert_case.id} from "
                f"'{alert_case.queue_status.value}'; allowed statuses: {allowed}"
            )

    def _append_admin_audit_log(
        self,
        *,
        admin: AdminUser,
        action_code: str,
        alert_case: AlertCase,
        ip_address: str | None,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        """Append one admin audit event for a manual alert action."""
        self.repository.add_audit_log(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                actor_id=admin.id,
                action_code=action_code,
                target_type="alert_case",
                target_id=alert_case.id,
                metadata_json=metadata_json,
                ip_address=ip_address,
            )
        )

    def _append_system_audit_log(
        self,
        *,
        action_code: str,
        alert_case: AlertCase,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        """Append one system-generated audit event tied to an alert case."""
        self.repository.add_audit_log(
            AuditLog(
                actor_type=AuditActorType.SYSTEM,
                actor_id=None,
                action_code=action_code,
                target_type="alert_case",
                target_id=alert_case.id,
                metadata_json=metadata_json,
                ip_address=None,
            )
        )

    def _build_simulated_notice_log(self, *, intervention_note: str) -> str:
        """Build the persisted simulated-notice string shown in alert details."""
        return f"{SIMULATED_NOTICE_PREFIX} Note: {intervention_note}"

    def _normalize_required_text(self, text: str, *, field_name: str) -> str:
        """Strip one required note field and ensure it is not blank."""
        normalized = text.strip()
        if not normalized:
            raise AlertReviewServiceError(f"{field_name} must not be empty")
        return normalized
