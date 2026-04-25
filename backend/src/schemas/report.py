"""Request and response schemas for student report APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from src.constants.questionnaire_enums import (
    AssessmentReportType,
    QuestionnaireRiskLevel,
)


class ReportSummaryData(BaseModel):
    """Payload returned by `GET /api/v1/reports/summary`."""

    model_config = ConfigDict(extra="forbid")

    summary: dict[str, Any]


class ReportSummarySuccessResponse(BaseModel):
    """Standard success envelope for report summary responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: ReportSummaryData


class FullReportResponse(BaseModel):
    """Serializable full-profile report payload returned by the API."""

    model_config = ConfigDict(extra="forbid")

    report_type: AssessmentReportType
    report_version: str
    source_submission_ids: list[int]
    risk_level: QuestionnaireRiskLevel
    result_title: str
    content: dict[str, Any]


class ReportFullData(BaseModel):
    """Payload returned by `GET /api/v1/reports/full`."""

    model_config = ConfigDict(extra="forbid")

    report: FullReportResponse


class ReportFullSuccessResponse(BaseModel):
    """Standard success envelope for full-profile report responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: ReportFullData


class ReportHistoryItemResponse(BaseModel):
    """One report-history list entry for the student client."""

    model_config = ConfigDict(extra="forbid")

    report_type: AssessmentReportType
    questionnaire_code: str
    questionnaire_name: str
    submitted_at: datetime
    result_title: str
    risk_level: QuestionnaireRiskLevel
    hard_trigger_hit: bool
    flow_step: str | None
    score_summary: list[dict[str, Any]]
    summary_text: str


class ReportHistoryData(BaseModel):
    """Payload returned by `GET /api/v1/reports/history`."""

    model_config = ConfigDict(extra="forbid")

    records: list[ReportHistoryItemResponse]


class ReportHistorySuccessResponse(BaseModel):
    """Standard success envelope for report-history responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: ReportHistoryData
