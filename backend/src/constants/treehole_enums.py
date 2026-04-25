"""Enumerations for treehole posting, AI analysis, and post reactions."""

from __future__ import annotations

from enum import StrEnum


class TreeholeAIStatus(StrEnum):
    """Supported AI processing states for treehole posts."""

    PENDING = "pending"
    ANALYZED = "analyzed"
    MOCKED = "mocked"
    FAILED = "failed"


class TreeholePublishStatus(StrEnum):
    """Supported publication lifecycle states for treehole posts."""

    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    BLOCKED_HIGH_RISK = "blocked_high_risk"
    DELETED_BY_USER = "deleted_by_user"
    HIDDEN_BY_ADMIN = "hidden_by_admin"


class AIAnalysisTargetType(StrEnum):
    """Supported AI analysis target types."""

    TREEHOLE_POST = "treehole_post"


class AIAnalysisProvider(StrEnum):
    """Supported AI analysis providers."""

    DEEPSEEK = "deepseek"


class AIRecommendedAction(StrEnum):
    """Supported follow-up actions recommended by the AI analysis."""

    PUBLISH = "publish"
    FOCUS_LIST = "focus_list"
    MANUAL_REVIEW_HIGH = "manual_review_high"


class PostReactionType(StrEnum):
    """Supported preset reaction types on published treehole posts."""

    HUG = "hug"
    LIGHT = "light"
    ACCOMPANY = "accompany"
