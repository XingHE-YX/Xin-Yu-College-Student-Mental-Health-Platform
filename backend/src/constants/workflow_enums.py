"""Enumerations for alert review, intervention, focus tracking, and audit logs."""

from __future__ import annotations

from enum import StrEnum


class CaseSourceType(StrEnum):
    """Supported sources that can produce alerts or focus-list entries."""

    TREEHOLE = "treehole"
    ASSESSMENT = "assessment"
    HISTORY = "history"


class AlertCaseLevel(StrEnum):
    """Supported severity levels for alert cases."""

    WATCH = "watch"
    HIGH = "high"


class AlertQueueStatus(StrEnum):
    """Supported workflow statuses for alert-case review queues."""

    PENDING_REVIEW = "pending_review"
    CONFIRMED_PENDING_INTERVENTION = "confirmed_pending_intervention"
    DISMISSED_FALSE_POSITIVE = "dismissed_false_positive"
    CLOSED = "closed"


class ReviewPriority(StrEnum):
    """Supported manual-review priorities."""

    NORMAL = "normal"
    URGENT = "urgent"
    HIGHEST = "highest"


class InterventionActionType(StrEnum):
    """Supported intervention timeline actions."""

    CONFIRM_HIGH_RISK = "confirm_high_risk"
    DISMISS_FALSE_POSITIVE = "dismiss_false_positive"
    SIMULATE_CONTACT = "simulate_contact"
    ADD_NOTE = "add_note"
    CLOSE_CASE = "close_case"


class FocusListStatus(StrEnum):
    """Supported lifecycle states for focus-list entries."""

    ACTIVE = "active"
    RESOLVED = "resolved"


class AuditActorType(StrEnum):
    """Supported actor identities in audit records."""

    STUDENT = "student"
    ADMIN = "admin"
    SYSTEM = "system"
