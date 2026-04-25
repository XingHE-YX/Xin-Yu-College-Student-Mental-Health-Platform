"""Service layer for student-facing treehole feed, posting, and reactions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from src.constants.account_enums import ConsentStatus
from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.treehole_enums import (
    AIRecommendedAction,
    PostReactionType,
    TreeholeAIStatus,
    TreeholePublishStatus,
)
from src.models.ai_analysis_record import AIAnalysisRecord
from src.models.base import utc_now
from src.models.post_reaction import PostReaction
from src.models.student_user import StudentUser
from src.models.treehole_post import TreeholePost
from src.repositories.treehole_repository import TreeholeRepository

REACTION_DISPLAY_ORDER = (
    PostReactionType.HUG,
    PostReactionType.LIGHT,
    PostReactionType.ACCOMPANY,
)

PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)


class TreeholeServiceError(ValueError):
    """Base error for treehole service failures."""


class TreeholeConsentRequiredError(TreeholeServiceError):
    """Raised when a student without granted consent attempts to post."""


class TreeholeContentEmptyError(TreeholeServiceError):
    """Raised when a submitted treehole body is blank after normalization."""


class TreeholePostNotFoundError(TreeholeServiceError):
    """Raised when the requested treehole post does not exist for the caller."""


class TreeholePostNotPublicError(TreeholeServiceError):
    """Raised when the requested treehole post is not publicly interactable."""


@dataclass(frozen=True, slots=True)
class TreeholeReactionSnapshot:
    """Serialized reaction state for one preset support action."""

    reaction_type: PostReactionType
    count: int
    reacted_by_me: bool


@dataclass(frozen=True, slots=True)
class TreeholeFeedPostSnapshot:
    """Serialized feed state for one public treehole post."""

    post_id: int
    anonymous_name: str
    anonymous_avatar_key: str
    content: str
    published_at: datetime
    is_mine: bool
    total_reaction_count: int
    reactions: list[TreeholeReactionSnapshot]


@dataclass(frozen=True, slots=True)
class CreatedTreeholePostResult:
    """Created treehole post returned to the route layer."""

    post: TreeholePost


@dataclass(frozen=True, slots=True)
class TreeholeReactionResult:
    """Reaction submission result returned to the route layer."""

    post_id: int
    reaction_type: PostReactionType
    total_reaction_count: int
    reactions: list[TreeholeReactionSnapshot]


class TreeholeService:
    """Coordinate student feed reads, bootstrap post publishing, and reactions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TreeholeRepository(session)

    def list_feed(
        self,
        *,
        student_id: int,
        limit: int = 20,
    ) -> list[TreeholeFeedPostSnapshot]:
        """Return public treehole posts visible in the student feed."""
        posts = self.repository.list_public_posts(limit=limit)
        return [
            self._build_feed_post_snapshot(post, student_id=student_id)
            for post in posts
        ]

    def create_post(
        self,
        *,
        student: StudentUser,
        content: str,
    ) -> CreatedTreeholePostResult:
        """Persist one new treehole post using the phase-8 bootstrap publish path."""
        if student.consent_status is not ConsentStatus.GRANTED:
            raise TreeholeConsentRequiredError(
                "crisis intervention consent is required to create treehole posts"
            )

        normalized_content = self._normalize_content(content)
        if not normalized_content:
            raise TreeholeContentEmptyError("treehole content must not be empty")

        published_at = utc_now()
        post = TreeholePost(
            student_id=student.id,
            anonymous_name=student.display_nickname.strip() or "匿名同学",
            anonymous_avatar_key=student.display_avatar_seed,
            content_raw=normalized_content,
            content_masked=self._mask_content(normalized_content),
            ai_status=TreeholeAIStatus.MOCKED,
            publish_status=TreeholePublishStatus.PUBLISHED,
            risk_level=QuestionnaireRiskLevel.LOW,
            allow_publication=True,
            hug_count=0,
            published_at=published_at,
        )
        self.repository.add_post(post)
        self.session.add(self._build_bootstrap_analysis_record(post, normalized_content))
        self.session.commit()
        self.session.refresh(post)
        return CreatedTreeholePostResult(post=post)

    def delete_post(
        self,
        *,
        student_id: int,
        post_id: int,
    ) -> TreeholePost:
        """Soft-delete one owned treehole post while keeping the database record."""
        post = self.repository.get_student_post(post_id=post_id, student_id=student_id)
        if post is None:
            raise TreeholePostNotFoundError("treehole post does not exist")

        if post.publish_status is not TreeholePublishStatus.DELETED_BY_USER:
            post.publish_status = TreeholePublishStatus.DELETED_BY_USER
            post.allow_publication = False
            post.deleted_at = post.deleted_at or utc_now()
            self.session.commit()
            self.session.refresh(post)
        return post

    def submit_reaction(
        self,
        *,
        student_id: int,
        post_id: int,
        reaction_type: PostReactionType,
    ) -> TreeholeReactionResult:
        """Record one preset reaction on a public post, treating duplicates idempotently."""
        post = self.repository.get_post_by_id(post_id, include_reactions=True)
        if post is None:
            raise TreeholePostNotFoundError("treehole post does not exist")
        if not self._is_public_post(post):
            raise TreeholePostNotPublicError(
                "treehole reactions are only allowed on published public posts"
            )

        existing_reaction = self.repository.get_reaction(
            post_id=post_id,
            student_id=student_id,
            reaction_type=reaction_type,
        )
        if existing_reaction is None:
            self.repository.add_reaction(
                PostReaction(
                    post_id=post_id,
                    student_id=student_id,
                    reaction_type=reaction_type,
                )
            )
            # `hug_count` stores the total support reaction count for quick summaries.
            post.hug_count += 1
            self.session.commit()
            self.session.expire_all()
            post = self.repository.get_post_by_id(post_id, include_reactions=True)
            if post is None:
                raise TreeholePostNotFoundError("treehole post does not exist")

        reactions = self._build_reaction_snapshots(post, student_id=student_id)
        return TreeholeReactionResult(
            post_id=post.id,
            reaction_type=reaction_type,
            total_reaction_count=post.hug_count,
            reactions=reactions,
        )

    def _build_feed_post_snapshot(
        self,
        post: TreeholePost,
        *,
        student_id: int,
    ) -> TreeholeFeedPostSnapshot:
        """Serialize one ORM post row into the feed response shape."""
        if post.content_masked is None or post.published_at is None:
            raise TreeholePostNotPublicError(
                "treehole feed only supports posts with masked public content"
            )

        return TreeholeFeedPostSnapshot(
            post_id=post.id,
            anonymous_name=post.anonymous_name,
            anonymous_avatar_key=post.anonymous_avatar_key,
            content=post.content_masked,
            published_at=post.published_at,
            is_mine=post.student_id == student_id,
            total_reaction_count=post.hug_count,
            reactions=self._build_reaction_snapshots(post, student_id=student_id),
        )

    def _build_reaction_snapshots(
        self,
        post: TreeholePost,
        *,
        student_id: int,
    ) -> list[TreeholeReactionSnapshot]:
        """Aggregate all stored reactions into the fixed student-facing chip order."""
        count_by_type = {reaction_type: 0 for reaction_type in REACTION_DISPLAY_ORDER}
        reacted_types: set[PostReactionType] = set()
        for reaction in post.reactions:
            count_by_type[reaction.reaction_type] = (
                count_by_type.get(reaction.reaction_type, 0) + 1
            )
            if reaction.student_id == student_id:
                reacted_types.add(reaction.reaction_type)

        return [
            TreeholeReactionSnapshot(
                reaction_type=reaction_type,
                count=count_by_type[reaction_type],
                reacted_by_me=reaction_type in reacted_types,
            )
            for reaction_type in REACTION_DISPLAY_ORDER
        ]

    def _build_bootstrap_analysis_record(
        self,
        post: TreeholePost,
        content: str,
    ) -> AIAnalysisRecord:
        """Create the phase-8 placeholder analysis row used before phase-9 AI wiring."""
        return AIAnalysisRecord(
            target_id=post.id,
            request_payload_json={
                "mode": "stage_8_bootstrap",
                "content_length": len(content),
            },
            response_raw_json={
                "mode": "stage_8_bootstrap",
                "risk_level": QuestionnaireRiskLevel.LOW.value,
                "publish_status": TreeholePublishStatus.PUBLISHED.value,
            },
            parsed_risk_level=QuestionnaireRiskLevel.LOW,
            parsed_risk_score=Decimal("0.1200"),
            emotion_tags_json=["stage_8_bootstrap"],
            trigger_phrases_json=[],
            reason_text=(
                "Phase 8 bootstrap moderation auto-published this post so the "
                "student feed, reaction, and delete flows can run before phase 9 "
                "AI integration lands."
            ),
            recommended_action=AIRecommendedAction.PUBLISH,
            fallback_used=True,
        )

    def _is_public_post(self, post: TreeholePost) -> bool:
        """Return whether one stored post is still visible in the public feed."""
        return (
            post.publish_status is TreeholePublishStatus.PUBLISHED
            and post.allow_publication
            and post.deleted_at is None
            and post.published_at is not None
            and post.content_masked is not None
        )

    def _normalize_content(self, content: str) -> str:
        """Normalize student-entered content while preserving paragraph breaks."""
        return content.replace("\r\n", "\n").strip()

    def _mask_content(self, content: str) -> str:
        """Apply lightweight contact-info masking before content enters the feed."""
        masked_content = PHONE_PATTERN.sub("[手机号已隐藏]", content)
        masked_content = EMAIL_PATTERN.sub("[邮箱已隐藏]", masked_content)
        return masked_content
