"""Student report routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.core.auth import get_current_student
from src.core.database import get_db_session
from src.models.student_user import StudentUser
from src.schemas.report import (
    FullReportResponse,
    ReportDeleteData,
    ReportDeleteSuccessResponse,
    ReportFullData,
    ReportFullSuccessResponse,
    ReportHistoryData,
    ReportHistoryItemResponse,
    ReportHistorySuccessResponse,
    ReportSummaryData,
    ReportSummarySuccessResponse,
)
from src.services.assessment_report_service import (
    AssessmentReportConfigurationError,
    FullProfileLockedError,
)
from src.services.student_report_service import (
    ReportSubmissionNotFoundError,
    StudentReportService,
)

router = APIRouter(prefix="/reports", tags=["reports"])


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


@router.get(
    "/summary",
    response_model=ReportSummarySuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_report_summary(
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportSummarySuccessResponse | JSONResponse:
    """Return the report-home summary payload for the current student."""
    try:
        summary = StudentReportService(session).build_report_summary(student_id=student.id)
    except AssessmentReportConfigurationError as exc:
        return build_error_response(
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="REPORT_CONFIGURATION_UNAVAILABLE",
            message=str(exc),
        )

    return ReportSummarySuccessResponse(
        request_id=build_request_id(),
        data=ReportSummaryData(summary=summary),
    )


@router.get(
    "/full",
    response_model=ReportFullSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_full_profile_report(
    request: Request,
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportFullSuccessResponse | JSONResponse:
    """Return the unlocked full-profile report for the current student."""
    try:
        report = StudentReportService(
            session,
            deepseek_service=request.app.state.deepseek_service,
        ).build_full_profile_report(student_id=student.id)
    except FullProfileLockedError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="FULL_PROFILE_LOCKED",
            message=str(exc),
        )
    except AssessmentReportConfigurationError as exc:
        return build_error_response(
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="REPORT_CONFIGURATION_UNAVAILABLE",
            message=str(exc),
        )

    return ReportFullSuccessResponse(
        request_id=build_request_id(),
        data=ReportFullData(
            report=FullReportResponse(
                report_type=report.report_type,
                report_version=report.report_version,
                source_submission_ids=report.source_submission_ids,
                risk_level=report.risk_level,
                result_title=report.result_title,
                content=report.content,
            )
        ),
    )


@router.get(
    "/history",
    response_model=ReportHistorySuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_report_history(
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportHistorySuccessResponse | JSONResponse:
    """Return report-history items for the current student."""
    try:
        history = StudentReportService(session).build_report_history(student_id=student.id)
    except AssessmentReportConfigurationError as exc:
        return build_error_response(
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="REPORT_CONFIGURATION_UNAVAILABLE",
            message=str(exc),
        )

    return ReportHistorySuccessResponse(
        request_id=build_request_id(),
        data=ReportHistoryData(
            records=[
                ReportHistoryItemResponse(
                    report_type=item.report_type,
                    submission_id=item.submission_id,
                    questionnaire_code=item.questionnaire_code,
                    questionnaire_name=item.questionnaire_name,
                    submitted_at=item.submitted_at,
                    result_title=item.result_title,
                    risk_level=item.risk_level,
                    hard_trigger_hit=item.hard_trigger_hit,
                    flow_step=item.flow_step,
                    score_summary=item.score_summary,
                    summary_text=item.summary_text,
                )
                for item in history
            ]
        ),
    )


@router.delete(
    "/history/{submission_id}",
    response_model=ReportDeleteSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def delete_report_history_item(
    submission_id: int,
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportDeleteSuccessResponse | JSONResponse:
    """Soft-delete one student-visible report history item."""
    try:
        submission = StudentReportService(session).delete_report_history_item(
            student_id=student.id,
            submission_id=submission_id,
        )
    except ReportSubmissionNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="REPORT_HISTORY_ITEM_NOT_FOUND",
            message=str(exc),
        )

    assert submission.deleted_at is not None
    return ReportDeleteSuccessResponse(
        request_id=build_request_id(),
        data=ReportDeleteData(
            submission_id=submission.id,
            deleted_at=submission.deleted_at,
        ),
    )
