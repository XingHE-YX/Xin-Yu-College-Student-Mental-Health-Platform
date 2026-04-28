"""Repository helpers for administrator treehole post management queries."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.constants.treehole_enums import TreeholePublishStatus
from src.models.audit_log import AuditLog
from src.models.post_reaction import PostReaction
from src.models.treehole_post import TreeholePost


class AdminPostRepository:
    """Load post-management rows and persist audited admin visibility actions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_posts(
        self,
        *,
        publish_status: TreeholePublishStatus | None,
    ) -> list[TreeholePost]:
        """Return posts for A05 ordered by latest visible activity."""
        ordering_expression = func.coalesce(
            TreeholePost.published_at,
            TreeholePost.deleted_at,
            TreeholePost.created_at,
        )
        statement = (
            select(TreeholePost)
            .options(selectinload(TreeholePost.student))
            .order_by(ordering_expression.desc(), TreeholePost.id.desc())
        )
        if publish_status is not None:
            statement = statement.where(TreeholePost.publish_status == publish_status)
        return list(self.session.scalars(statement).all())

    def count_posts_by_status(self) -> dict[TreeholePublishStatus, int]:
        """Return post counts grouped by publication status."""
        rows = self.session.execute(
            select(TreeholePost.publish_status, func.count()).group_by(
                TreeholePost.publish_status
            )
        ).all()
        return {publish_status: int(count) for publish_status, count in rows}

    def get_post_detail(self, post_id: int) -> TreeholePost | None:
        """Return one post with relationships required by the A05 detail pane."""
        statement = (
            select(TreeholePost)
            .options(
                selectinload(TreeholePost.student),
                selectinload(TreeholePost.reactions),
                selectinload(TreeholePost.ai_analysis_records),
                selectinload(TreeholePost.alert_cases),
            )
            .where(TreeholePost.id == post_id)
        )
        return self.session.scalar(statement)

    def get_post_by_id(self, post_id: int) -> TreeholePost | None:
        """Return one post by primary key without loading extra relationships."""
        statement = select(TreeholePost).where(TreeholePost.id == post_id)
        return self.session.scalar(statement)

    def add_audit_log(self, audit_log: AuditLog) -> AuditLog:
        """Stage one audit event created by admin post management actions."""
        self.session.add(audit_log)
        self.session.flush()
        return audit_log

    def list_reactions(self, *, post_id: int) -> list[PostReaction]:
        """Return all preset support reactions for one treehole post."""
        statement = select(PostReaction).where(PostReaction.post_id == post_id)
        return list(self.session.scalars(statement).all())
