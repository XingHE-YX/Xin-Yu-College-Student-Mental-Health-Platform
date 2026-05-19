"""ORM model for questionnaire submission records."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.questionnaire_enums import (
    QuestionnaireRiskLevel,
    QuestionnaireSubmissionStatus,
)
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    DATETIME_3,
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    PrimaryKeyMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.alert_case import AlertCase
    from src.models.questionnaire_answer import QuestionnaireAnswer
    from src.models.questionnaire_template import QuestionnaireTemplate
    from src.models.student_user import StudentUser


class QuestionnaireSubmission(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist each completed questionnaire submission and its scoring snapshot."""

    __tablename__ = "questionnaire_submissions"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    student_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("student_users.id"),
        nullable=False,
    )
    template_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("questionnaire_templates.id"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DATETIME_3, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DATETIME_3, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME_3, nullable=True)
    status: Mapped[QuestionnaireSubmissionStatus] = mapped_column(
        Enum(
            QuestionnaireSubmissionStatus,
            name="questionnaire_submission_status_enum",
            values_callable=enum_values,
        ),
        default=QuestionnaireSubmissionStatus.SUBMITTED,
        nullable=False,
    )
    raw_score: Mapped[int] = mapped_column(Integer, nullable=False)
    standardized_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[QuestionnaireRiskLevel] = mapped_column(
        Enum(
            QuestionnaireRiskLevel,
            name="questionnaire_risk_level_enum",
            values_callable=enum_values,
        ),
        default=QuestionnaireRiskLevel.LOW,
        nullable=False,
    )
    hard_trigger_hit: Mapped[bool] = mapped_column(default=False, nullable=False)
    scoring_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    student: Mapped[StudentUser] = relationship(
        back_populates="questionnaire_submissions"
    )
    template: Mapped[QuestionnaireTemplate] = relationship(back_populates="submissions")
    answers: Mapped[list[QuestionnaireAnswer]] = relationship(
        back_populates="submission"
    )
    alert_cases: Mapped[list[AlertCase]] = relationship(
        back_populates="source_submission"
    )
