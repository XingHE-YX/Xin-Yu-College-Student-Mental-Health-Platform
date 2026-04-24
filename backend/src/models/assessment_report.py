"""ORM model for generated questionnaire result and profile reports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.questionnaire_enums import (
    AssessmentReportType,
    QuestionnaireRiskLevel,
)
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    PrimaryKeyMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.student_user import StudentUser


class AssessmentReport(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist scale result reports and the final combined full profile."""

    __tablename__ = "assessment_reports"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    student_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("student_users.id"),
        nullable=False,
    )
    report_type: Mapped[AssessmentReportType] = mapped_column(
        Enum(
            AssessmentReportType,
            name="assessment_report_type_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    report_version: Mapped[str] = mapped_column(String(16), nullable=False)
    source_submission_ids_json: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    risk_level: Mapped[QuestionnaireRiskLevel] = mapped_column(
        Enum(
            QuestionnaireRiskLevel,
            name="assessment_report_risk_level_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    result_title: Mapped[str] = mapped_column(String(128), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    student: Mapped[StudentUser] = relationship(back_populates="assessment_reports")
