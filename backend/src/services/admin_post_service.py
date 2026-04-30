"""Service layer for administrator treehole post management views and actions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from src.constants.treehole_enums import PostReactionType, TreeholePublishStatus
from src.constants.workflow_enums import AuditActorType
from src.models.audit_log import AuditLog
from src.models.base import utc_now
from src.models.post_reaction import PostReaction
from src.models.treehole_post import TreeholePost
from src.repositories.admin_post_repository import AdminPostRepository

POST_STATUS_DISPLAY_ORDER = (
    TreeholePublishStatus.PUBLISHED,
    TreeholePublishStatus.HIDDEN_BY_ADMIN,
    TreeholePublishStatus.BLOCKED_HIGH_RISK,
    TreeholePublishStatus.DELETED_BY_USER,
)
POST_STATUS_LABELS = {
    TreeholePublishStatus.PUBLISHED: "已发布",
    TreeholePublishStatus.HIDDEN_BY_ADMIN: "管理员隐藏",
    TreeholePublishStatus.BLOCKED_HIGH_RISK: "被拦截",
    TreeholePublishStatus.DELETED_BY_USER: "已删除",
}
POST_REACTION_DISPLAY_ORDER = (
    PostReactionType.HUG,
    PostReactionType.LIGHT,
    PostReactionType.ACCOMPANY,
)
POST_REACTION_LABELS = {
    PostReactionType.HUG: "抱抱",
    PostReactionType.LIGHT: "点亮",
    PostReactionType.ACCOMPANY: "陪伴",
}
VISIBILITY_ACTION_LABELS = {
    "hide": "隐藏帖子",
    "keep_hidden": "保持隐藏",
    "restore_publish": "恢复发布",
}


class AdminPostServiceError(ValueError):
    """Base error raised when administrator post management cannot proceed."""


class AdminPostNotFoundError(AdminPostServiceError):
    """Raised when one requested treehole post does not exist."""


class PostSourceContentUnavailableError(AdminPostServiceError):
    """Raised when one requested treehole post has no revealable raw content."""


class InvalidPostVisibilityTransitionError(AdminPostServiceError):
    """Raised when one admin visibility action is incompatible with the post state."""


@dataclass(frozen=True, slots=True)
class PostStatusCount:
    """One publish-status count bucket used by the A05 filter controls."""

    publish_status: TreeholePublishStatus
    count: int


@dataclass(frozen=True, slots=True)
class AdminPostListItem:
    """Compact post row shown in the left-side A05 management list."""

    post_id: int
    created_at: Any
    publish_status: TreeholePublishStatus
    risk_level: str
    anonymous_name: str
    source_preview: str
    student_label: str
    masked_phone: str
    college_name: str
    class_name: str
    total_reaction_count: int
    published_at: Any
    deleted_at: Any


@dataclass(frozen=True, slots=True)
class AdminPostListSnapshot:
    """Serialized A05 list payload returned to the route layer."""

    applied_publish_status: TreeholePublishStatus | None
    status_counts: list[PostStatusCount]
    items: list[AdminPostListItem]


@dataclass(frozen=True, slots=True)
class AdminPostVisibilityResult:
    """Result of one administrator visibility action."""

    post: TreeholePost
    action: str


class AdminPostService:
    """Build A05 post snapshots and apply audited admin visibility actions."""

    def __init__(self, session: Session, *, show_seeded_cases: bool = True) -> None:
        self.session = session
        self.repository = AdminPostRepository(session)
        self.show_seeded_cases = show_seeded_cases

    def list_posts(
        self,
        *,
        publish_status: TreeholePublishStatus | None,
    ) -> AdminPostListSnapshot:
        """Return the filtered A05 post list and grouped status counts."""
        counts_by_status = self.repository.count_posts_by_status(
            show_seeded_cases=self.show_seeded_cases
        )
        items = [
            self._build_list_item(post)
            for post in self.repository.list_posts(
                publish_status=publish_status,
                show_seeded_cases=self.show_seeded_cases,
            )
        ]
        return AdminPostListSnapshot(
            applied_publish_status=publish_status,
            status_counts=[
                PostStatusCount(
                    publish_status=status,
                    count=counts_by_status.get(status, 0),
                )
                for status in POST_STATUS_DISPLAY_ORDER
            ],
            items=items,
        )

    def get_post_detail(self, *, post_id: int) -> dict[str, Any]:
        """Return one A05 post detail payload without exposing raw content by default."""
        post = self._load_post_detail(post_id)
        return self._build_post_detail_payload(post, include_full_content=False)

    def reveal_post_content(
        self,
        *,
        post_id: int,
        admin_user_id: int,
        ip_address: str | None,
    ) -> dict[str, Any]:
        """Return `content_raw` for one post and audit the sensitive reveal."""
        post = self._load_post_detail(post_id)
        if not post.content_raw.strip():
            raise PostSourceContentUnavailableError(
                f"treehole post '{post_id}' has no revealable raw content"
            )

        self._append_audit_log(
            admin_user_id=admin_user_id,
            action_code="ADMIN_REVEAL_POST_CONTENT",
            target_type="treehole_post",
            target_id=post.id,
            ip_address=ip_address,
            metadata_json={
                "publish_status": post.publish_status.value,
                "risk_level": post.risk_level.value,
            },
        )
        self.session.commit()
        return {
            "post_id": post.id,
            "full_content": post.content_raw,
        }

    def update_visibility(
        self,
        *,
        post_id: int,
        admin_user_id: int,
        action: str,
        ip_address: str | None,
    ) -> AdminPostVisibilityResult:
        """Apply one audited admin visibility action to the selected treehole post."""
        normalized_action = action.strip()
        if normalized_action not in VISIBILITY_ACTION_LABELS:
            raise InvalidPostVisibilityTransitionError(
                f"unsupported post visibility action '{normalized_action}'"
            )

        post = self._load_post(post_id)
        previous_status = post.publish_status

        if normalized_action == "hide":
            self._hide_post(post)
            audit_code = "ADMIN_HIDE_POST"
        elif normalized_action == "keep_hidden":
            self._keep_post_hidden(post)
            audit_code = "ADMIN_KEEP_POST_HIDDEN"
        else:
            self._restore_post_visibility(post)
            audit_code = "ADMIN_RESTORE_POST_VISIBILITY"

        self._append_audit_log(
            admin_user_id=admin_user_id,
            action_code=audit_code,
            target_type="treehole_post",
            target_id=post.id,
            ip_address=ip_address,
            metadata_json={
                "action": normalized_action,
                "previous_status": previous_status.value,
                "next_status": post.publish_status.value,
            },
        )
        self.session.commit()
        self.session.refresh(post)
        return AdminPostVisibilityResult(post=post, action=normalized_action)

    def _build_list_item(self, post: TreeholePost) -> AdminPostListItem:
        """Serialize one treehole post into the compact A05 list-row shape."""
        student = post.student
        if student is None:
            raise AdminPostNotFoundError(
                f"treehole post '{post.id}' is missing its student relation"
            )

        preview = self._resolve_post_preview(post)
        return AdminPostListItem(
            post_id=post.id,
            created_at=post.created_at,
            publish_status=post.publish_status,
            risk_level=post.risk_level.value,
            anonymous_name=post.anonymous_name,
            source_preview=preview,
            student_label=self._build_student_label(student.id),
            masked_phone=self._mask_phone(student.phone_e164),
            college_name=student.college_name,
            class_name=student.class_name,
            total_reaction_count=post.hug_count,
            published_at=post.published_at,
            deleted_at=post.deleted_at,
        )

    def _build_post_detail_payload(
        self,
        post: TreeholePost,
        *,
        include_full_content: bool,
    ) -> dict[str, Any]:
        """Serialize one managed treehole post into the A05 detail payload shape."""
        student = post.student
        if student is None:
            raise AdminPostNotFoundError(
                f"treehole post '{post.id}' is missing its student relation"
            )

        latest_analysis = self._select_latest_ai_analysis(post)
        return {
            "post_id": post.id,
            "created_at": post.created_at,
            "publish_status": post.publish_status.value,
            "publish_status_label": POST_STATUS_LABELS[post.publish_status],
            "risk_level": post.risk_level.value,
            "anonymous_name": post.anonymous_name,
            "anonymous_avatar_key": post.anonymous_avatar_key,
            "published_at": post.published_at,
            "deleted_at": post.deleted_at,
            "allow_publication": post.allow_publication,
            "student": {
                "student_label": self._build_student_label(student.id),
                "masked_phone": self._mask_phone(student.phone_e164),
                "college_name": student.college_name,
                "class_name": student.class_name,
                "risk_status": student.risk_status.value,
            },
            "content": {
                "masked_content": self._resolve_masked_content(post),
                "full_content_available": bool(post.content_raw.strip()),
                "full_content": post.content_raw if include_full_content else None,
            },
            "ai_analysis": self._serialize_ai_analysis(latest_analysis),
            "reactions": self._build_reaction_summary(post.reactions),
            "alert_case_summary": self._build_alert_case_summary(post),
            "action_permissions": self._build_action_permissions(post),
        }

    def _select_latest_ai_analysis(self, post: TreeholePost):
        """Return the latest AI analysis record already loaded on the ORM post."""
        if not post.ai_analysis_records:
            return None
        return max(
            post.ai_analysis_records,
            key=lambda record: (record.created_at, record.id),
        )

    def _build_reaction_summary(
        self,
        reactions: list[PostReaction],
    ) -> list[dict[str, Any]]:
        """Aggregate preset support reactions into a fixed display order."""
        count_by_type = {reaction_type: 0 for reaction_type in POST_REACTION_DISPLAY_ORDER}
        for reaction in reactions:
            count_by_type[reaction.reaction_type] = (
                count_by_type.get(reaction.reaction_type, 0) + 1
            )

        return [
            {
                "reaction_type": reaction_type.value,
                "label": POST_REACTION_LABELS[reaction_type],
                "count": count_by_type[reaction_type],
            }
            for reaction_type in POST_REACTION_DISPLAY_ORDER
        ]

    def _build_alert_case_summary(self, post: TreeholePost) -> dict[str, Any] | None:
        """Return the latest linked alert-case summary for blocked posts, if present."""
        if not post.alert_cases:
            return None
        latest_case = max(
            post.alert_cases,
            key=lambda alert_case: (alert_case.created_at, alert_case.id),
        )
        return {
            "alert_id": latest_case.id,
            "queue_status": latest_case.queue_status.value,
            "review_priority": latest_case.review_priority.value,
            "review_note": latest_case.review_note,
        }

    def _build_action_permissions(self, post: TreeholePost) -> dict[str, bool]:
        """Return which A05 visibility actions should currently be shown."""
        can_hide = post.publish_status is TreeholePublishStatus.PUBLISHED
        can_keep_hidden = post.publish_status in {
            TreeholePublishStatus.HIDDEN_BY_ADMIN,
            TreeholePublishStatus.BLOCKED_HIGH_RISK,
        }
        can_restore_publish = post.publish_status is TreeholePublishStatus.HIDDEN_BY_ADMIN
        return {
            "can_hide": can_hide,
            "can_keep_hidden": can_keep_hidden,
            "can_restore_publish": can_restore_publish,
        }

    def _resolve_post_preview(self, post: TreeholePost) -> str:
        """Return the compact preview shown inside one A05 post list card."""
        if post.content_masked:
            return self._truncate_text(post.content_masked)
        if post.publish_status is TreeholePublishStatus.BLOCKED_HIGH_RISK:
            return "该内容因高风险被系统拦截，默认不在列表中直接展示原文。"
        if post.publish_status is TreeholePublishStatus.DELETED_BY_USER:
            return "该内容已被学生前端软删除，仅后台在受控条件下可查看。"
        return "该内容当前处于隐藏状态，仅在管理员工作区受控展示。"

    def _resolve_masked_content(self, post: TreeholePost) -> str:
        """Return the masked content block used by the A05 detail pane."""
        if post.content_masked:
            return post.content_masked
        if post.publish_status is TreeholePublishStatus.BLOCKED_HIGH_RISK:
            return "该高风险内容已被系统拦截，默认仅展示动作与分析结果，原文需显式展开。"
        if post.publish_status is TreeholePublishStatus.DELETED_BY_USER:
            return "该内容已被学生前端软删除，原文仅在管理员确认后才会展开。"
        return "该内容当前已被管理员隐藏，原文仅在管理员确认后才会展开。"

    def _serialize_ai_analysis(self, analysis_record) -> dict[str, Any] | None:
        """Return the treehole AI analysis block for one managed post."""
        if analysis_record is None:
            return None
        risk_score = analysis_record.parsed_risk_score
        return {
            "parsed_risk_level": analysis_record.parsed_risk_level.value,
            "parsed_risk_score": self._serialize_decimal(risk_score),
            "emotion_tags": list(analysis_record.emotion_tags_json),
            "trigger_phrases": list(analysis_record.trigger_phrases_json),
            "reason_text": analysis_record.reason_text,
            "recommended_action": analysis_record.recommended_action.value,
            "fallback_used": analysis_record.fallback_used,
        }

    def _hide_post(self, post: TreeholePost) -> None:
        """Hide one currently published post from the public feed."""
        if post.publish_status is not TreeholePublishStatus.PUBLISHED:
            raise InvalidPostVisibilityTransitionError(
                f"cannot hide post {post.id} from '{post.publish_status.value}'"
            )
        post.publish_status = TreeholePublishStatus.HIDDEN_BY_ADMIN
        post.allow_publication = False

    def _keep_post_hidden(self, post: TreeholePost) -> None:
        """Persist an explicit admin decision to keep the post non-public."""
        if post.publish_status not in {
            TreeholePublishStatus.HIDDEN_BY_ADMIN,
            TreeholePublishStatus.BLOCKED_HIGH_RISK,
        }:
            raise InvalidPostVisibilityTransitionError(
                f"cannot keep post {post.id} hidden from '{post.publish_status.value}'"
            )

    def _restore_post_visibility(self, post: TreeholePost) -> None:
        """Restore one admin-hidden post back to the public feed."""
        if post.publish_status is not TreeholePublishStatus.HIDDEN_BY_ADMIN:
            raise InvalidPostVisibilityTransitionError(
                f"cannot restore post {post.id} from '{post.publish_status.value}'"
            )
        post.publish_status = TreeholePublishStatus.PUBLISHED
        post.allow_publication = True
        if post.published_at is None:
            post.published_at = utc_now()

    def _append_audit_log(
        self,
        *,
        admin_user_id: int,
        action_code: str,
        target_type: str,
        target_id: int,
        ip_address: str | None,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        """Persist one admin audit event related to A05 reveal or visibility actions."""
        self.repository.add_audit_log(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                actor_id=admin_user_id,
                action_code=action_code,
                target_type=target_type,
                target_id=target_id,
                metadata_json=metadata_json,
                ip_address=ip_address,
            )
        )

    def _load_post_detail(self, post_id: int) -> TreeholePost:
        """Load one managed post with detail relationships or raise a business error."""
        post = self.repository.get_post_detail(
            post_id,
            show_seeded_cases=self.show_seeded_cases,
        )
        if post is None:
            raise AdminPostNotFoundError(f"treehole post '{post_id}' does not exist")
        return post

    def _load_post(self, post_id: int) -> TreeholePost:
        """Load one managed post without extra relations or raise a business error."""
        post = self.repository.get_post_by_id(
            post_id,
            show_seeded_cases=self.show_seeded_cases,
        )
        if post is None:
            raise AdminPostNotFoundError(f"treehole post '{post_id}' does not exist")
        return post

    def _build_student_label(self, student_id: int) -> str:
        """Return one stable masked student identifier used across admin pages."""
        return f"STU-{student_id:06d}"

    def _mask_phone(self, phone_number: str) -> str:
        """Return a lightly masked phone string for admin list/detail views."""
        if len(phone_number) <= 6:
            return phone_number[:1] + "***"
        return f"{phone_number[:5]}****{phone_number[-2:]}"

    def _truncate_text(self, text: str, *, max_length: int = 68) -> str:
        """Clamp one list-page preview string without breaking the admin layout."""
        normalized = " ".join(text.split())
        if len(normalized) <= max_length:
            return normalized
        return f"{normalized[: max_length - 1]}…"

    def _serialize_decimal(self, value: Decimal) -> float:
        """Convert one Decimal risk score into a JSON-friendly float."""
        return float(value)
