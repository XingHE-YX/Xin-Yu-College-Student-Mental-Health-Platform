"""ORM model for persisted AI analysis records."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.treehole_enums import (
    AIAnalysisProvider,
    AIAnalysisTargetType,
    AIRecommendedAction,
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
    from src.models.treehole_post import TreeholePost


class AIAnalysisRecord(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist AI request, raw response, and structured interpretation."""

    __tablename__ = "ai_analysis_records"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    target_type: Mapped[AIAnalysisTargetType] = mapped_column(
        Enum(
            AIAnalysisTargetType,
            name="ai_analysis_target_type_enum",
            values_callable=enum_values,
        ),
        default=AIAnalysisTargetType.TREEHOLE_POST,
        nullable=False,
    )
    target_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("treehole_posts.id"),
        nullable=False,
    )
    provider: Mapped[AIAnalysisProvider] = mapped_column(
        Enum(
            AIAnalysisProvider,
            name="ai_analysis_provider_enum",
            values_callable=enum_values,
        ),
        default=AIAnalysisProvider.DEEPSEEK,
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(64), default="deepseek-chat", nullable=False
    )
    request_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    response_raw_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    parsed_risk_level: Mapped[QuestionnaireRiskLevel] = mapped_column(
        Enum(
            QuestionnaireRiskLevel,
            name="ai_analysis_risk_level_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    parsed_risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    emotion_tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    trigger_phrases_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[AIRecommendedAction] = mapped_column(
        Enum(
            AIRecommendedAction,
            name="ai_recommended_action_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    fallback_used: Mapped[bool] = mapped_column(default=False, nullable=False)

    post: Mapped[TreeholePost] = relationship(back_populates="ai_analysis_records")
