"""Request and response schemas for administrator post-management APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.constants.treehole_enums import TreeholePublishStatus


class AdminPostListItemResponse(BaseModel):
    """Compact post row returned by `GET /api/v1/admin/posts`."""

    model_config = ConfigDict(extra="forbid")

    post_id: int
    created_at: datetime
    publish_status: TreeholePublishStatus
    risk_level: str
    anonymous_name: str
    source_preview: str
    student_label: str
    masked_phone: str
    college_name: str
    class_name: str
    total_reaction_count: int
    published_at: datetime | None
    deleted_at: datetime | None


class AdminPostStatusCountResponse(BaseModel):
    """One publish-status count bucket for the A05 filter controls."""

    model_config = ConfigDict(extra="forbid")

    publish_status: TreeholePublishStatus
    count: int


class AdminPostListData(BaseModel):
    """Data payload returned by `GET /api/v1/admin/posts`."""

    model_config = ConfigDict(extra="forbid")

    applied_publish_status: TreeholePublishStatus | None
    status_counts: list[AdminPostStatusCountResponse]
    items: list[AdminPostListItemResponse]


class AdminPostListSuccessResponse(BaseModel):
    """Standard success envelope for admin post list responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminPostListData


class AdminPostDetailData(BaseModel):
    """Data payload returned by `GET /api/v1/admin/posts/{post_id}`."""

    model_config = ConfigDict(extra="forbid")

    post: dict[str, Any]


class AdminPostDetailSuccessResponse(BaseModel):
    """Standard success envelope for admin post detail responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminPostDetailData


class AdminPostRevealContentData(BaseModel):
    """Data payload returned after explicitly revealing treehole raw content."""

    model_config = ConfigDict(extra="forbid")

    post_id: int
    full_content: str


class AdminPostRevealContentSuccessResponse(BaseModel):
    """Standard success envelope for raw-content reveal responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminPostRevealContentData


class AdminPostVisibilityUpdateRequest(BaseModel):
    """Payload for `PATCH /api/v1/admin/posts/{post_id}/visibility`."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["hide", "keep_hidden", "restore_publish"] = Field(
        description="管理员帖子可见性动作。"
    )


class AdminPostVisibilityUpdateData(BaseModel):
    """Data payload returned after one admin post visibility action."""

    model_config = ConfigDict(extra="forbid")

    post_id: int
    publish_status: TreeholePublishStatus
    allow_publication: bool
    action: str


class AdminPostVisibilityUpdateSuccessResponse(BaseModel):
    """Standard success envelope for visibility update responses."""

    model_config = ConfigDict(extra="forbid")

    code: Literal["OK"] = "OK"
    message: Literal["success"] = "success"
    request_id: str
    data: AdminPostVisibilityUpdateData
