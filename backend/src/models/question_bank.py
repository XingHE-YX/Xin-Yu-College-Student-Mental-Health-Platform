"""ORM model for questionnaire question bank entries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.questionnaire_enums import QuestionType
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    MYSQL_TABLE_OPTIONS,
    SMALLINT_UNSIGNED,
    Base,
    CreatedAtMixin,
    PrimaryKeyMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.questionnaire_answer import QuestionnaireAnswer
    from src.models.questionnaire_template import QuestionnaireTemplate


class QuestionBank(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist questionnaire questions imported from local appendix seed files."""

    __tablename__ = "question_bank"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    template_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("questionnaire_templates.id"),
        nullable=False,
    )
    question_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    question_order: Mapped[int] = mapped_column(SMALLINT_UNSIGNED, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(
            QuestionType,
            name="question_type_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    score_mapping_json: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    reverse_scored: Mapped[bool] = mapped_column(default=False, nullable=False)
    hard_trigger_rule_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    seed_source: Mapped[str] = mapped_column(String(128), nullable=False)

    template: Mapped[QuestionnaireTemplate] = relationship(back_populates="questions")
    answers: Mapped[list[QuestionnaireAnswer]] = relationship(back_populates="question")
