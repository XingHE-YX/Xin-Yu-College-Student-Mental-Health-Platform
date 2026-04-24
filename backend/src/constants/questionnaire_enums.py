"""Enumerations for questionnaire, submission, and report database fields."""

from __future__ import annotations

from enum import StrEnum


class QuestionnaireCategory(StrEnum):
    """Supported questionnaire participation categories."""

    REQUIRED = "required"
    OPTIONAL = "optional"


class QuestionnaireScoringMode(StrEnum):
    """Supported scoring strategies for questionnaire templates."""

    SUM_1_5 = "sum_1_5"
    SUM_0_3 = "sum_0_3"
    ZUNG_STANDARD = "zung_standard"
    YES_NO = "yes_no"


class QuestionType(StrEnum):
    """Supported question rendering and answer types."""

    SINGLE_CHOICE = "single_choice"
    YES_NO = "yes_no"


class QuestionnaireSubmissionStatus(StrEnum):
    """Supported submission lifecycle states."""

    SUBMITTED = "submitted"
    SCORED = "scored"


class QuestionnaireRiskLevel(StrEnum):
    """Supported questionnaire and report risk levels."""

    LOW = "low"
    WATCH = "watch"
    HIGH = "high"


class AssessmentReportType(StrEnum):
    """Supported assessment report categories."""

    SCALE_RESULT = "scale_result"
    FULL_PROFILE = "full_profile"
