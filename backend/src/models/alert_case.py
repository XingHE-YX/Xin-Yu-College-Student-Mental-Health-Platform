"""ORM model for alert review queue cases."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    CaseSourceType,
    ReviewPriority,
)
from src.models.base import (
    BIGINT_PRIMARY_KEY,
    DATETIME_3,
    MYSQL_TABLE_OPTIONS,
    Base,
    PrimaryKeyMixin,
    TimestampMixin,
    enum_values,
)

if TYPE_CHECKING:
    from src.models.admin_user import AdminUser
    from src.models.intervention_log import InterventionLog
    from src.models.questionnaire_submission import QuestionnaireSubmission
    from src.models.student_user import StudentUser
    from src.models.treehole_post import TreeholePost


class AlertCase(PrimaryKeyMixin, TimestampMixin, Base):
    """Persist alert-case metadata, queue status, and review outcome."""

    __tablename__ = "alert_cases"
    __table_args__ = MYSQL_TABLE_OPTIONS.copy()

    student_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("student_users.id"),
        nullable=False,
    )
    source_type: Mapped[CaseSourceType] = mapped_column(
        Enum(
            CaseSourceType,
            name="case_source_type_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    source_post_id: Mapped[int | None] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("treehole_posts.id"),
        nullable=True,
    )
    source_submission_id: Mapped[int | None] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("questionnaire_submissions.id"),
        nullable=True,
    )
    case_level: Mapped[AlertCaseLevel] = mapped_column(
        Enum(
            AlertCaseLevel,
            name="alert_case_level_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    queue_status: Mapped[AlertQueueStatus] = mapped_column(
        Enum(
            AlertQueueStatus,
            name="alert_queue_status_enum",
            values_callable=enum_values,
        ),
        default=AlertQueueStatus.PENDING_REVIEW,
        nullable=False,
    )
    review_priority: Mapped[ReviewPriority] = mapped_column(
        Enum(
            ReviewPriority,
            name="review_priority_enum",
            values_callable=enum_values,
        ),
        default=ReviewPriority.NORMAL,
        nullable=False,
    )
    ai_reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("admin_users.id"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DATETIME_3, nullable=True)
    simulated_notice_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    student: Mapped[StudentUser] = relationship(back_populates="alert_cases")
    source_post: Mapped[TreeholePost | None] = relationship(
        back_populates="alert_cases"
    )
    source_submission: Mapped[QuestionnaireSubmission | None] = relationship(
        back_populates="alert_cases"
    )
    reviewer: Mapped[AdminUser | None] = relationship(
        back_populates="reviewed_alert_cases"
    )
    intervention_logs: Mapped[list[InterventionLog]] = relationship(
        back_populates="alert_case"
    )
