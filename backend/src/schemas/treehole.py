"""Request and response schemas for student treehole APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.treehole_enums import PostReactionType, TreeholePublishStatus


class TreeholeReactionResponse(BaseModel):
    """One preset support reaction summary shown in the student client."""

    model_config = ConfigDict(extra="forbid")

    reaction_type: PostReactionType
    label: str
    count: int
    reacted_by_me: bool


class TreeholeFeedPostResponse(BaseModel):
    """One public feed post returned to the student client."""

    model_config = ConfigDict(extra="forbid")

    post_id: int
    anonymous_name: str
    anonymous_avatar_key: str
    content: str
    published_at: datetime
    is_mine: bool
    total_reaction_count: int
    reactions: list[TreeholeReactionResponse]


class TreeholeFeedData(BaseModel):
    """Payload returned by `GET /api/v1/treehole/feed`."""

    model_config = ConfigDict(extra="forbid")

    posts: list[TreeholeFeedPostResponse]


class TreeholeFeedSuccessResponse(BaseModel):
    """Standard success envelope for treehole feed responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: TreeholeFeedData


class TreeholeCreatePostRequest(BaseModel):
    """Payload for `POST /api/v1/treehole/posts`."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)


class TreeholeCreatePostData(BaseModel):
    """Business payload returned after creating one treehole post."""

    model_config = ConfigDict(extra="forbid")

    post_id: int
    risk_level: QuestionnaireRiskLevel
    publish_status: TreeholePublishStatus
    allow_publication: bool
    anonymous_name: str
    anonymous_avatar_key: str
    content_masked: str | None
    published_at: datetime | None
    hotline: str | None = None


class TreeholeCreatePostSuccessResponse(BaseModel):
    """Standard success envelope for treehole create responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: TreeholeCreatePostData


class TreeholeDeletePostData(BaseModel):
    """Business payload returned after soft-deleting one treehole post."""

    model_config = ConfigDict(extra="forbid")

    post_id: int
    publish_status: TreeholePublishStatus
    deleted_at: datetime | None


class TreeholeDeletePostSuccessResponse(BaseModel):
    """Standard success envelope for treehole delete responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: TreeholeDeletePostData


class TreeholeReactionRequest(BaseModel):
    """Payload for `POST /api/v1/treehole/posts/{post_id}/reactions`."""

    model_config = ConfigDict(extra="forbid")

    reaction_type: PostReactionType


class TreeholeReactionData(BaseModel):
    """Business payload returned after submitting one reaction."""

    model_config = ConfigDict(extra="forbid")

    post_id: int
    reaction_type: PostReactionType
    total_reaction_count: int
    reactions: list[TreeholeReactionResponse]


class TreeholeReactionSuccessResponse(BaseModel):
    """Standard success envelope for treehole reaction responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: TreeholeReactionData
