"""ORM model for per-question answer records inside a submission."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import (
    BIGINT_PRIMARY_KEY,
    MYSQL_TABLE_OPTIONS,
    Base,
    CreatedAtMixin,
    PrimaryKeyMixin,
)

if TYPE_CHECKING:
    from src.models.question_bank import QuestionBank
    from src.models.questionnaire_submission import QuestionnaireSubmission


class QuestionnaireAnswer(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist each normalized answer belonging to a questionnaire submission."""

    __tablename__ = "questionnaire_answers"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    submission_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("questionnaire_submissions.id"),
        nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("question_bank.id"),
        nullable=False,
    )
    selected_option: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_value: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_score: Mapped[int] = mapped_column(Integer, nullable=False)

    submission: Mapped[QuestionnaireSubmission] = relationship(back_populates="answers")
    question: Mapped[QuestionBank] = relationship(back_populates="answers")
