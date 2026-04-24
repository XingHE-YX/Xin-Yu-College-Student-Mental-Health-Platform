"""ORM model for questionnaire template metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireScoringMode,
)
from src.models.base import (
    MYSQL_TABLE_OPTIONS,
    SMALLINT_UNSIGNED,
    Base,
    CreatedAtMixin,
    PrimaryKeyMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.question_bank import QuestionBank
    from src.models.questionnaire_submission import QuestionnaireSubmission


class QuestionnaireTemplate(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist metadata about each questionnaire available in the system."""

    __tablename__ = "questionnaire_templates"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[QuestionnaireCategory] = mapped_column(
        Enum(
            QuestionnaireCategory,
            name="questionnaire_category_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    question_count: Mapped[int] = mapped_column(SMALLINT_UNSIGNED, nullable=False)
    scoring_mode: Mapped[QuestionnaireScoringMode] = mapped_column(
        Enum(
            QuestionnaireScoringMode,
            name="questionnaire_scoring_mode_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    unlock_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    questions: Mapped[list[QuestionBank]] = relationship(back_populates="template")
    submissions: Mapped[list[QuestionnaireSubmission]] = relationship(back_populates="template")
