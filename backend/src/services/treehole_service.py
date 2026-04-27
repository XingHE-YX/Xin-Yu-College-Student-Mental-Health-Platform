"""Service layer for student-facing treehole feed, posting, and reactions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from src.constants.account_enums import ConsentStatus, StudentRiskStatus
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
from src.repositories.student_user_repository import StudentUserRepository
from src.repositories.treehole_repository import TreeholeRepository
from src.services.alert_case_service import AlertCaseService
from src.services.deepseek_service import DeepSeekJsonCompletionResult, DeepSeekService
from src.services.focus_list_service import FocusListService
from src.services.risk_aggregation_service import (
    AggregatedRiskResult,
    RiskAggregationService,
)

REACTION_DISPLAY_ORDER = (
    PostReactionType.HUG,
    PostReactionType.LIGHT,
    PostReactionType.ACCOMPANY,
)
TREEHOLE_HOTLINE_PHONE = "400-161-9995"

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


class TreeholeAIAnalysisError(TreeholeServiceError):
    """Raised when one AI analysis payload cannot be normalized for persistence."""


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


@dataclass(frozen=True, slots=True)
class TreeholeAIAnalysisSnapshot:
    """Normalized treehole AI moderation result used for persistence."""

    parsed_risk_level: QuestionnaireRiskLevel
    parsed_risk_score: Decimal
    emotion_tags: list[str]
    trigger_phrases: list[str]
    reason_text: str
    recommended_action: AIRecommendedAction
    request_payload_json: dict[str, object]
    response_raw_json: dict[str, object]
    fallback_used: bool
    ai_status: TreeholeAIStatus


class TreeholeService:
    """Coordinate student feed reads, AI-backed post publishing, and reactions."""

    def __init__(
        self,
        session: Session,
        *,
        deepseek_service: DeepSeekService | None = None,
    ) -> None:
        self.session = session
        self.repository = TreeholeRepository(session)
        self.alert_case_service = AlertCaseService(session)
        self.focus_list_service = FocusListService(session)
        self.student_repository = StudentUserRepository(session)
        self.risk_aggregation_service = RiskAggregationService(session)
        self.deepseek_service = deepseek_service

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
        """Persist one new treehole post and apply the phase-9 publication decision rules."""
        if student.consent_status is not ConsentStatus.GRANTED:
            raise TreeholeConsentRequiredError(
                "crisis intervention consent is required to create treehole posts"
            )

        normalized_content = self._normalize_content(content)
        if not normalized_content:
            raise TreeholeContentEmptyError("treehole content must not be empty")

        published_at = utc_now()
        masked_content = self._mask_content(normalized_content)
        post = TreeholePost(
            student_id=student.id,
            anonymous_name=student.display_nickname.strip() or "匿名同学",
            anonymous_avatar_key=student.display_avatar_seed,
            content_raw=normalized_content,
            content_masked=None,
            ai_status=TreeholeAIStatus.PENDING,
            publish_status=TreeholePublishStatus.PENDING_REVIEW,
            risk_level=QuestionnaireRiskLevel.LOW,
            allow_publication=False,
            hug_count=0,
            published_at=None,
        )
        self.repository.add_post(post)
        analysis_snapshot = self._analyze_treehole_content(normalized_content)
        aggregated_risk = self.risk_aggregation_service.aggregate_treehole_risk(
            student=student,
            ai_risk_level=analysis_snapshot.parsed_risk_level,
        )
        self._apply_publish_decision(
            post=post,
            masked_content=masked_content,
            published_at=published_at,
            aggregated_risk=aggregated_risk,
        )
        self._apply_student_risk_status(
            student=student,
            aggregated_risk=aggregated_risk,
        )
        post.ai_status = analysis_snapshot.ai_status
        self.session.add(self._build_ai_analysis_record(post, analysis_snapshot))
        self._create_follow_up_records(
            student=student,
            post=post,
            analysis_snapshot=analysis_snapshot,
            aggregated_risk=aggregated_risk,
        )
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

    def _build_ai_analysis_record(
        self,
        post: TreeholePost,
        analysis_snapshot: TreeholeAIAnalysisSnapshot,
    ) -> AIAnalysisRecord:
        """Create one persisted AI analysis row from a normalized moderation snapshot."""
        return AIAnalysisRecord(
            target_id=post.id,
            request_payload_json=analysis_snapshot.request_payload_json,
            response_raw_json=analysis_snapshot.response_raw_json,
            parsed_risk_level=analysis_snapshot.parsed_risk_level,
            parsed_risk_score=analysis_snapshot.parsed_risk_score,
            emotion_tags_json=analysis_snapshot.emotion_tags,
            trigger_phrases_json=analysis_snapshot.trigger_phrases,
            reason_text=analysis_snapshot.reason_text,
            recommended_action=analysis_snapshot.recommended_action,
            fallback_used=analysis_snapshot.fallback_used,
        )

    def _apply_publish_decision(
        self,
        *,
        post: TreeholePost,
        masked_content: str,
        published_at: datetime,
        aggregated_risk: AggregatedRiskResult,
    ) -> None:
        """Map the aggregated risk level into publication state and public fields."""
        post.risk_level = aggregated_risk.risk_level
        if aggregated_risk.risk_level is QuestionnaireRiskLevel.HIGH:
            post.publish_status = TreeholePublishStatus.BLOCKED_HIGH_RISK
            post.allow_publication = False
            post.published_at = None
            post.content_masked = None
            return

        post.publish_status = TreeholePublishStatus.PUBLISHED
        post.allow_publication = True
        post.published_at = published_at
        post.content_masked = masked_content

    def _apply_student_risk_status(
        self,
        *,
        student: StudentUser,
        aggregated_risk: AggregatedRiskResult,
    ) -> None:
        """Persist the student's latest aggregate risk without prematurely downgrading history."""
        next_risk_status = student.risk_status
        if aggregated_risk.risk_level is QuestionnaireRiskLevel.HIGH:
            next_risk_status = StudentRiskStatus.HIGH
        elif aggregated_risk.risk_level is QuestionnaireRiskLevel.WATCH:
            next_risk_status = (
                StudentRiskStatus.HIGH
                if student.risk_status is StudentRiskStatus.HIGH
                else StudentRiskStatus.WATCH
            )

        if next_risk_status is not student.risk_status:
            self.student_repository.update_risk_status(
                student,
                risk_status=next_risk_status,
            )

    def _create_follow_up_records(
        self,
        *,
        student: StudentUser,
        post: TreeholePost,
        analysis_snapshot: TreeholeAIAnalysisSnapshot,
        aggregated_risk: AggregatedRiskResult,
    ) -> None:
        """Create watch-list or alert records from the final publication decision."""
        if aggregated_risk.risk_level is QuestionnaireRiskLevel.WATCH:
            self.focus_list_service.create_treehole_watch_entry(
                student_id=student.id,
                post_id=post.id,
                reason_code=aggregated_risk.reason_codes[0],
                reason_text=self._build_follow_up_reason_text(
                    analysis_snapshot=analysis_snapshot,
                    aggregated_risk=aggregated_risk,
                ),
            )
            return

        if aggregated_risk.risk_level is QuestionnaireRiskLevel.HIGH:
            self.alert_case_service.create_treehole_high_risk_case(
                student_id=student.id,
                post_id=post.id,
                reason_text=self._build_follow_up_reason_text(
                    analysis_snapshot=analysis_snapshot,
                    aggregated_risk=aggregated_risk,
                ),
            )

    def _build_follow_up_reason_text(
        self,
        *,
        analysis_snapshot: TreeholeAIAnalysisSnapshot,
        aggregated_risk: AggregatedRiskResult,
    ) -> str:
        """Build a stable human-readable reason for watch-list and alert records."""
        reason_prefix = "；".join(aggregated_risk.reason_codes)
        history_hint = (
            "系统同时检测到历史高风险记录，本次建议纳入复查。"
            if aggregated_risk.history_elevated
            else ""
        )
        if history_hint:
            return f"{analysis_snapshot.reason_text}（{reason_prefix}）。{history_hint}"
        return f"{analysis_snapshot.reason_text}（{reason_prefix}）。"

    def _analyze_treehole_content(
        self,
        content: str,
    ) -> TreeholeAIAnalysisSnapshot:
        """Run DeepSeek moderation with local fallback and normalize the structured result."""
        if self.deepseek_service is None:
            return self._build_legacy_mock_analysis_snapshot(content)

        completion_result = self.deepseek_service.create_json_completion_with_fallback(
            system_prompt=(
                "You are a campus mental-health safety moderation assistant for an "
                "anonymous treehole product. Analyze the student text and return a "
                "structured safety assessment. Do not diagnose. Focus on risk "
                "signals, supportive context, and whether the content can stay public."
            ),
            user_prompt=(
                "Analyze the following anonymous treehole post:\n"
                f"{content}"
            ),
            response_example={
                "risk_level": "low",
                "risk_score": 0.12,
                "emotion_tags": ["fatigue"],
                "trigger_phrases": [],
                "reason_text": "brief rationale",
                "recommended_action": "publish",
            },
        )
        return self._normalize_ai_completion_result(completion_result)

    def _normalize_ai_completion_result(
        self,
        completion_result: DeepSeekJsonCompletionResult,
    ) -> TreeholeAIAnalysisSnapshot:
        """Normalize one DeepSeek or mock completion into the persistence snapshot."""
        content_json = completion_result.content_json

        risk_level_raw = content_json.get("risk_level")
        try:
            parsed_risk_level = QuestionnaireRiskLevel(str(risk_level_raw))
        except ValueError as exc:
            raise TreeholeAIAnalysisError(
                "treehole AI analysis payload contains an invalid risk_level"
            ) from exc

        risk_score_raw = content_json.get("risk_score", "0")
        try:
            parsed_risk_score = Decimal(str(risk_score_raw)).quantize(
                Decimal("0.0001")
            )
        except (InvalidOperation, ValueError) as exc:
            raise TreeholeAIAnalysisError(
                "treehole AI analysis payload contains an invalid risk_score"
            ) from exc

        emotion_tags = self._normalize_string_list(
            content_json.get("emotion_tags", []),
            field_name="emotion_tags",
        )
        trigger_phrases = self._normalize_string_list(
            content_json.get("trigger_phrases", []),
            field_name="trigger_phrases",
        )
        reason_text = content_json.get("reason_text")
        if not isinstance(reason_text, str) or not reason_text.strip():
            raise TreeholeAIAnalysisError(
                "treehole AI analysis payload contains an invalid reason_text"
            )

        recommended_action_raw = content_json.get("recommended_action")
        try:
            recommended_action = AIRecommendedAction(str(recommended_action_raw))
        except ValueError as exc:
            raise TreeholeAIAnalysisError(
                "treehole AI analysis payload contains an invalid recommended_action"
            ) from exc

        return TreeholeAIAnalysisSnapshot(
            parsed_risk_level=parsed_risk_level,
            parsed_risk_score=parsed_risk_score,
            emotion_tags=emotion_tags,
            trigger_phrases=trigger_phrases,
            reason_text=reason_text.strip(),
            recommended_action=recommended_action,
            request_payload_json=completion_result.request_payload,
            response_raw_json=completion_result.response_payload,
            fallback_used=completion_result.fallback_used,
            ai_status=(
                TreeholeAIStatus.MOCKED
                if completion_result.fallback_used
                else TreeholeAIStatus.ANALYZED
            ),
        )

    def _build_legacy_mock_analysis_snapshot(
        self,
        content: str,
    ) -> TreeholeAIAnalysisSnapshot:
        """Fallback snapshot used only when the app is missing a DeepSeek service instance."""
        return TreeholeAIAnalysisSnapshot(
            parsed_risk_level=QuestionnaireRiskLevel.LOW,
            parsed_risk_score=Decimal("0.1200"),
            emotion_tags=["stage_9_fallback"],
            trigger_phrases=[],
            reason_text=(
                "Treehole moderation used the local fallback path because no "
                "DeepSeek service instance was attached to the application."
            ),
            recommended_action=AIRecommendedAction.PUBLISH,
            request_payload_json={
                "mode": "missing_deepseek_service",
                "content_length": len(content),
            },
            response_raw_json={
                "source": "legacy_missing_service_fallback",
                "risk_level": QuestionnaireRiskLevel.LOW.value,
                "recommended_action": AIRecommendedAction.PUBLISH.value,
            },
            fallback_used=True,
            ai_status=TreeholeAIStatus.MOCKED,
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

    def _normalize_string_list(
        self,
        value: object,
        *,
        field_name: str,
    ) -> list[str]:
        """Validate that one AI payload field is a string array and trim empty items."""
        if not isinstance(value, list):
            raise TreeholeAIAnalysisError(
                f"treehole AI analysis payload contains an invalid {field_name}"
            )

        normalized_items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise TreeholeAIAnalysisError(
                    f"treehole AI analysis payload contains an invalid {field_name}"
                )
            normalized_item = item.strip()
            if normalized_item:
                normalized_items.append(normalized_item)
        return normalized_items
