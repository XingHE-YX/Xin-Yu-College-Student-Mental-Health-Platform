"""Student questionnaire metadata and progress routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.core.auth import get_current_student
from src.core.database import get_db_session
from src.models.student_user import StudentUser
from src.schemas.questionnaire import (
    QuestionnaireDetailData,
    QuestionnaireDetailResponse,
    QuestionnaireDetailSuccessResponse,
    QuestionnaireLatestSubmissionResponse,
    QuestionnaireListData,
    QuestionnaireListItemResponse,
    QuestionnaireListSuccessResponse,
    QuestionnaireOptionResponse,
    QuestionnaireProgressData,
    QuestionnaireProgressResponse,
    QuestionnaireProgressSuccessResponse,
    QuestionnaireQuestionResponse,
    RequiredProgressQuestionnaireResponse,
)
from src.services.questionnaire_query_service import (
    LatestSubmissionSummary,
    QuestionnaireCatalogUnavailableError,
    QuestionnaireDetailEntry,
    QuestionnaireNotFoundError,
    QuestionnaireProgressSnapshot,
    QuestionnaireQueryService,
)

router = APIRouter(prefix="/questionnaires", tags=["questionnaires"])


def build_request_id() -> str:
    """Return a short opaque request identifier for API envelopes."""
    return uuid4().hex


def build_error_response(
    *,
    http_status: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Return a business-style error envelope."""
    return JSONResponse(
        status_code=http_status,
        content={
            "code": code,
            "message": message,
            "request_id": build_request_id(),
        },
    )


def build_latest_submission_response(
    latest_submission: LatestSubmissionSummary | None,
) -> QuestionnaireLatestSubmissionResponse | None:
    """Serialize one latest-submission summary into the API response shape."""
    if latest_submission is None:
        return None

    return QuestionnaireLatestSubmissionResponse(
        submission_id=latest_submission.submission_id,
        submitted_at=latest_submission.submitted_at,
        raw_score=latest_submission.raw_score,
        standardized_score=latest_submission.standardized_score,
        risk_level=latest_submission.risk_level,
        hard_trigger_hit=latest_submission.hard_trigger_hit,
    )


def build_questionnaire_detail_response(
    detail: QuestionnaireDetailEntry,
) -> QuestionnaireDetailResponse:
    """Serialize questionnaire detail data into the API response shape."""
    return QuestionnaireDetailResponse(
        code=detail.code,
        name=detail.name,
        category=detail.category,
        scoring_mode=detail.scoring_mode,
        question_count=detail.question_count,
        unlock_required=detail.unlock_required,
        is_active=detail.is_active,
        flow_step=detail.flow_step,
        latest_submission=build_latest_submission_response(detail.latest_submission),
        questions=[
            QuestionnaireQuestionResponse(
                question_code=question.question_code,
                question_order=question.question_order,
                question_text=question.question_text,
                question_type=question.question_type,
                options=[
                    QuestionnaireOptionResponse(
                        value=option.value,
                        label=option.label,
                    )
                    for option in question.options
                ],
            )
            for question in detail.questions
        ],
    )


def build_progress_response(
    progress: QuestionnaireProgressSnapshot,
) -> QuestionnaireProgressResponse:
    """Serialize the student's required-questionnaire progress snapshot."""
    return QuestionnaireProgressResponse(
        completed_required_questionnaires=progress.completed_required_questionnaires,
        total_required_questionnaires=progress.total_required_questionnaires,
        completed_required_questions=progress.completed_required_questions,
        total_required_questions=progress.total_required_questions,
        full_profile_unlocked=progress.full_profile_unlocked,
        required_questionnaires=[
            RequiredProgressQuestionnaireResponse(
                code=entry.code,
                name=entry.name,
                question_count=entry.question_count,
                flow_step=entry.flow_step,
                completed=entry.completed,
                latest_submission=build_latest_submission_response(
                    entry.latest_submission
                ),
            )
            for entry in progress.required_questionnaires
        ],
    )


@router.get(
    "",
    response_model=QuestionnaireListSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def list_questionnaires(
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> QuestionnaireListSuccessResponse | JSONResponse:
    """Return all active questionnaires for the authenticated student."""
    try:
        questionnaire_entries = QuestionnaireQueryService(session).list_questionnaires(
            student_id=student.id
        )
    except QuestionnaireCatalogUnavailableError as exc:
        return build_error_response(
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="QUESTIONNAIRE_CATALOG_UNAVAILABLE",
            message=str(exc),
        )

    return QuestionnaireListSuccessResponse(
        request_id=build_request_id(),
        data=QuestionnaireListData(
            questionnaires=[
                QuestionnaireListItemResponse(
                    code=entry.code,
                    name=entry.name,
                    category=entry.category,
                    scoring_mode=entry.scoring_mode,
                    question_count=entry.question_count,
                    unlock_required=entry.unlock_required,
                    is_active=entry.is_active,
                    flow_step=entry.flow_step,
                    latest_submission=build_latest_submission_response(
                        entry.latest_submission
                    ),
                )
                for entry in questionnaire_entries
            ]
        ),
    )


@router.get(
    "/progress",
    response_model=QuestionnaireProgressSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_questionnaire_progress(
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> QuestionnaireProgressSuccessResponse | JSONResponse:
    """Return the current student's progress across the fixed 70-question chain."""
    try:
        progress = QuestionnaireQueryService(session).get_required_progress(
            student_id=student.id
        )
    except QuestionnaireCatalogUnavailableError as exc:
        return build_error_response(
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="QUESTIONNAIRE_CATALOG_UNAVAILABLE",
            message=str(exc),
        )

    return QuestionnaireProgressSuccessResponse(
        request_id=build_request_id(),
        data=QuestionnaireProgressData(progress=build_progress_response(progress)),
    )


@router.get(
    "/{questionnaire_code}",
    response_model=QuestionnaireDetailSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_questionnaire_detail(
    questionnaire_code: str,
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> QuestionnaireDetailSuccessResponse | JSONResponse:
    """Return renderable metadata for one questionnaire code."""
    try:
        detail = QuestionnaireQueryService(session).get_questionnaire_detail(
            student_id=student.id,
            questionnaire_code=questionnaire_code,
        )
    except QuestionnaireNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="QUESTIONNAIRE_NOT_FOUND",
            message=str(exc),
        )
    except QuestionnaireCatalogUnavailableError as exc:
        return build_error_response(
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="QUESTIONNAIRE_CATALOG_UNAVAILABLE",
            message=str(exc),
        )

    return QuestionnaireDetailSuccessResponse(
        request_id=build_request_id(),
        data=QuestionnaireDetailData(
            questionnaire=build_questionnaire_detail_response(detail)
        ),
    )
