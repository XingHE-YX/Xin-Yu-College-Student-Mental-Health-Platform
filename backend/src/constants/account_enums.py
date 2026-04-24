"""Enumerations for account and consent related database fields."""

from __future__ import annotations

from enum import StrEnum


class StudentRiskStatus(StrEnum):
    """Supported aggregate risk states for student accounts."""

    NORMAL = "normal"
    WATCH = "watch"
    HIGH = "high"


class ConsentStatus(StrEnum):
    """Supported consent states for student accounts."""

    GRANTED = "granted"
    DECLINED = "declined"
    MISSING = "missing"


class ConsentType(StrEnum):
    """Supported immutable consent record categories."""

    PRIVACY_POLICY = "privacy_policy"
    CRISIS_INTERVENTION_AUTHORIZATION = "crisis_intervention_authorization"


class AdminRoleCode(StrEnum):
    """Supported administrator role codes."""

    PLATFORM_ADMIN = "platform_admin"
    COUNSELOR = "counselor"
    ADVISOR = "advisor"
