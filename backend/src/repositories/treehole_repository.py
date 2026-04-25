"""Repository helpers for student-facing treehole APIs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.constants.treehole_enums import PostReactionType, TreeholePublishStatus
from src.models.post_reaction import PostReaction
from src.models.treehole_post import TreeholePost


class TreeholeRepository:
    """Persist and query treehole posts plus preset reactions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_public_posts(self, *, limit: int) -> list[TreeholePost]:
        """Return published posts for the public feed ordered by newest first."""
        statement = (
            select(TreeholePost)
            .options(selectinload(TreeholePost.reactions))
            .where(
                TreeholePost.publish_status == TreeholePublishStatus.PUBLISHED,
                TreeholePost.allow_publication.is_(True),
                TreeholePost.deleted_at.is_(None),
                TreeholePost.published_at.is_not(None),
                TreeholePost.content_masked.is_not(None),
            )
            .order_by(TreeholePost.published_at.desc(), TreeholePost.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def get_post_by_id(
        self,
        post_id: int,
        *,
        include_reactions: bool = False,
    ) -> TreeholePost | None:
        """Return one post by id, optionally with reaction rows loaded."""
        statement = select(TreeholePost).where(TreeholePost.id == post_id)
        if include_reactions:
            statement = statement.options(selectinload(TreeholePost.reactions))
        return self.session.scalar(statement)

    def get_student_post(
        self,
        *,
        post_id: int,
        student_id: int,
        include_reactions: bool = False,
    ) -> TreeholePost | None:
        """Return one owned post for the given student id."""
        statement = select(TreeholePost).where(
            TreeholePost.id == post_id,
            TreeholePost.student_id == student_id,
        )
        if include_reactions:
            statement = statement.options(selectinload(TreeholePost.reactions))
        return self.session.scalar(statement)

    def get_reaction(
        self,
        *,
        post_id: int,
        student_id: int,
        reaction_type: PostReactionType,
    ) -> PostReaction | None:
        """Return one existing reaction row for the same student and type."""
        statement = select(PostReaction).where(
            PostReaction.post_id == post_id,
            PostReaction.student_id == student_id,
            PostReaction.reaction_type == reaction_type,
        )
        return self.session.scalar(statement)

    def add_post(self, post: TreeholePost) -> TreeholePost:
        """Stage one new treehole post for persistence."""
        self.session.add(post)
        self.session.flush()
        return post

    def add_reaction(self, reaction: PostReaction) -> PostReaction:
        """Stage one new reaction for persistence."""
        self.session.add(reaction)
        self.session.flush()
        return reaction
