"""ORM model for anonymous treehole posts and publication state."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.treehole_enums import TreeholeAIStatus, TreeholePublishStatus
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    DATETIME_3,
    INT_UNSIGNED,
    MEDIUMTEXT,
    MYSQL_TABLE_OPTIONS,
    Base,
    PrimaryKeyMixin,
    TimestampMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.ai_analysis_record import AIAnalysisRecord
    from src.models.post_reaction import PostReaction
    from src.models.student_user import StudentUser


class TreeholePost(PrimaryKeyMixin, TimestampMixin, Base):
    """Persist treehole posts, anonymized content, and publication decisions."""

    __tablename__ = "treehole_posts"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    student_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("student_users.id"),
        nullable=False,
    )
    anonymous_name: Mapped[str] = mapped_column(String(64), nullable=False)
    anonymous_avatar_key: Mapped[str] = mapped_column(String(64), nullable=False)
    content_raw: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    content_masked: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    ai_status: Mapped[TreeholeAIStatus] = mapped_column(
        Enum(
            TreeholeAIStatus,
            name="treehole_ai_status_enum",
            values_callable=enum_values,
        ),
        default=TreeholeAIStatus.PENDING,
        nullable=False,
    )
    publish_status: Mapped[TreeholePublishStatus] = mapped_column(
        Enum(
            TreeholePublishStatus,
            name="treehole_publish_status_enum",
            values_callable=enum_values,
        ),
        default=TreeholePublishStatus.PENDING_REVIEW,
        nullable=False,
    )
    risk_level: Mapped[QuestionnaireRiskLevel] = mapped_column(
        Enum(
            QuestionnaireRiskLevel,
            name="treehole_risk_level_enum",
            values_callable=enum_values,
        ),
        default=QuestionnaireRiskLevel.LOW,
        nullable=False,
    )
    allow_publication: Mapped[bool] = mapped_column(default=False, nullable=False)
    hug_count: Mapped[int] = mapped_column(INT_UNSIGNED, default=0, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DATETIME_3, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME_3, nullable=True)

    student: Mapped[StudentUser] = relationship(back_populates="treehole_posts")
    ai_analysis_records: Mapped[list[AIAnalysisRecord]] = relationship(
        back_populates="post"
    )
    reactions: Mapped[list[PostReaction]] = relationship(back_populates="post")
