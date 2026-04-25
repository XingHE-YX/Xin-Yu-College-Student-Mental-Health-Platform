"""Request and response schemas for questionnaire metadata and submission APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionType,
)


class QuestionnaireLatestSubmissionResponse(BaseModel):
    """Latest student submission summary for one questionnaire."""

    model_config = ConfigDict(extra="forbid")

    submission_id: int
    submitted_at: datetime
    raw_score: int
    standardized_score: int | None
    risk_level: QuestionnaireRiskLevel
    hard_trigger_hit: bool


class QuestionnaireListItemResponse(BaseModel):
    """One questionnaire entry returned by the list endpoint."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    category: QuestionnaireCategory
    scoring_mode: QuestionnaireScoringMode
    question_count: int
    unlock_required: bool
    is_active: bool
    flow_step: str | None
    latest_submission: QuestionnaireLatestSubmissionResponse | None = None


class QuestionnaireListData(BaseModel):
    """Payload returned by `GET /api/v1/questionnaires`."""

    model_config = ConfigDict(extra="forbid")

    questionnaires: list[QuestionnaireListItemResponse]


class QuestionnaireListSuccessResponse(BaseModel):
    """Standard success envelope for questionnaire list responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: QuestionnaireListData


class QuestionnaireOptionResponse(BaseModel):
    """Renderable option metadata for one questionnaire question."""

    model_config = ConfigDict(extra="forbid")

    value: str
    label: str


class QuestionnaireQuestionResponse(BaseModel):
    """Renderable question payload returned by the detail endpoint."""

    model_config = ConfigDict(extra="forbid")

    question_code: str
    question_order: int
    question_text: str
    question_type: QuestionType
    options: list[QuestionnaireOptionResponse]


class QuestionnaireDetailResponse(BaseModel):
    """Questionnaire metadata and renderable questions."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    category: QuestionnaireCategory
    scoring_mode: QuestionnaireScoringMode
    question_count: int
    unlock_required: bool
    is_active: bool
    flow_step: str | None
    latest_submission: QuestionnaireLatestSubmissionResponse | None = None
    questions: list[QuestionnaireQuestionResponse]


class QuestionnaireDetailData(BaseModel):
    """Payload returned by `GET /api/v1/questionnaires/{code}`."""

    model_config = ConfigDict(extra="forbid")

    questionnaire: QuestionnaireDetailResponse


class QuestionnaireDetailSuccessResponse(BaseModel):
    """Standard success envelope for questionnaire detail responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: QuestionnaireDetailData


class RequiredProgressQuestionnaireResponse(BaseModel):
    """One required questionnaire entry inside the unlock-progress payload."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    question_count: int
    flow_step: str | None
    completed: bool
    latest_submission: QuestionnaireLatestSubmissionResponse | None = None


class QuestionnaireProgressResponse(BaseModel):
    """Fixed 70-question unlock-chain progress for the current student."""

    model_config = ConfigDict(extra="forbid")

    completed_required_questionnaires: int
    total_required_questionnaires: int
    completed_required_questions: int
    total_required_questions: int
    full_profile_unlocked: bool
    required_questionnaires: list[RequiredProgressQuestionnaireResponse]


class QuestionnaireProgressData(BaseModel):
    """Payload returned by `GET /api/v1/questionnaires/progress`."""

    model_config = ConfigDict(extra="forbid")

    progress: QuestionnaireProgressResponse


class QuestionnaireProgressSuccessResponse(BaseModel):
    """Standard success envelope for questionnaire progress responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: QuestionnaireProgressData


class SubmittedQuestionAnswerRequest(BaseModel):
    """One submitted answer inside a questionnaire submission payload."""

    model_config = ConfigDict(extra="forbid")

    question_code: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[A-Z][A-Z0-9_]*_\d{2}$",
    )
    selected_option: str = Field(min_length=1, max_length=32)


class QuestionnaireSubmissionRequest(BaseModel):
    """Payload for `POST /api/v1/questionnaires/{code}/submissions`."""

    model_config = ConfigDict(extra="forbid")

    answers: list[SubmittedQuestionAnswerRequest] = Field(min_length=1)


class QuestionnaireSubmissionResultData(BaseModel):
    """Business payload returned after scoring and persisting a submission."""

    model_config = ConfigDict(extra="forbid")

    submission_id: int
    questionnaire_code: str
    raw_score: int
    standardized_score: int | None
    risk_level: QuestionnaireRiskLevel
    hard_trigger_hit: bool


class QuestionnaireSubmissionSuccessResponse(BaseModel):
    """Standard success envelope for questionnaire submission responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: QuestionnaireSubmissionResultData
