"""ORM model for preset reactions on published treehole posts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.treehole_enums import PostReactionType
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
    from src.models.treehole_post import TreeholePost


class PostReaction(PrimaryKeyMixin, CreatedAtMixin, Base):
    """Persist non-text support reactions on treehole posts."""

    __tablename__ = "post_reactions"
    __table_args__ = (
        UniqueConstraint(
            "post_id",
            "student_id",
            "reaction_type",
            name="uq_post_reactions_post_id_student_id_reaction_type",
        ),
        MYSQL_TABLE_OPTIONS.copy(),
    )

    post_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("treehole_posts.id"),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        ForeignKey("student_users.id"),
        nullable=False,
    )
    reaction_type: Mapped[PostReactionType] = mapped_column(
        Enum(
            PostReactionType,
            name="post_reaction_type_enum",
            values_callable=enum_values,
        ),
        nullable=False,
    )

    post: Mapped[TreeholePost] = relationship(back_populates="reactions")
    student: Mapped[StudentUser] = relationship(back_populates="post_reactions")
