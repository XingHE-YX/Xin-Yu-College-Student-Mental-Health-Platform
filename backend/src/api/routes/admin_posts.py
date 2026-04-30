"""Administrator treehole post management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.constants.treehole_enums import TreeholePublishStatus
from src.core.auth import get_current_admin
from src.core.database import get_db_session
from src.models.admin_user import AdminUser
from src.schemas.admin_post import (
    AdminPostDetailData,
    AdminPostDetailSuccessResponse,
    AdminPostListData,
    AdminPostListItemResponse,
    AdminPostListSuccessResponse,
    AdminPostRevealContentData,
    AdminPostRevealContentSuccessResponse,
    AdminPostStatusCountResponse,
    AdminPostVisibilityUpdateData,
    AdminPostVisibilityUpdateRequest,
    AdminPostVisibilityUpdateSuccessResponse,
)
from src.services.admin_post_service import (
    AdminPostNotFoundError,
    AdminPostService,
    InvalidPostVisibilityTransitionError,
    PostSourceContentUnavailableError,
)

router = APIRouter(prefix="/admin/posts", tags=["admin-posts"])


def build_request_id() -> str:
    """Return a short opaque request identifier for API envelopes."""
    return uuid4().hex


def build_error_response(
    *,
    http_status: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Return a business-style error envelope."""
    return JSONResponse(
        status_code=http_status,
        content={
            "code": code,
            "message": message,
            "request_id": build_request_id(),
        },
    )


@router.get(
    "",
    response_model=AdminPostListSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def list_admin_posts(
    request: Request,
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    publish_status: TreeholePublishStatus | None = None,
) -> AdminPostListSuccessResponse:
    """Return the filtered A05 post list for the authenticated administrator."""
    post_snapshot = AdminPostService(
        session,
        show_seeded_cases=request.app.state.settings.show_seeded_cases,
    ).list_posts(publish_status=publish_status)
    return AdminPostListSuccessResponse(
        request_id=build_request_id(),
        data=AdminPostListData(
            applied_publish_status=post_snapshot.applied_publish_status,
            status_counts=[
                AdminPostStatusCountResponse(
                    publish_status=item.publish_status,
                    count=item.count,
                )
                for item in post_snapshot.status_counts
            ],
            items=[
                AdminPostListItemResponse(
                    post_id=item.post_id,
                    created_at=item.created_at,
                    publish_status=item.publish_status,
                    risk_level=item.risk_level,
                    anonymous_name=item.anonymous_name,
                    source_preview=item.source_preview,
                    student_label=item.student_label,
                    masked_phone=item.masked_phone,
                    college_name=item.college_name,
                    class_name=item.class_name,
                    total_reaction_count=item.total_reaction_count,
                    published_at=item.published_at,
                    deleted_at=item.deleted_at,
                )
                for item in post_snapshot.items
            ],
        ),
    )


@router.get(
    "/{post_id}",
    response_model=AdminPostDetailSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_admin_post_detail(
    post_id: int,
    request: Request,
    _admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminPostDetailSuccessResponse | JSONResponse:
    """Return one A05 post detail payload with masked content by default."""
    try:
        post_payload = AdminPostService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).get_post_detail(post_id=post_id)
    except AdminPostNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="TREEHOLE_POST_NOT_FOUND",
            message=str(exc),
        )

    return AdminPostDetailSuccessResponse(
        request_id=build_request_id(),
        data=AdminPostDetailData(post=post_payload),
    )


@router.post(
    "/{post_id}/reveal-content",
    response_model=AdminPostRevealContentSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def reveal_admin_post_content(
    post_id: int,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminPostRevealContentSuccessResponse | JSONResponse:
    """Reveal one post's raw content after explicit admin confirmation."""
    try:
        content_payload = AdminPostService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).reveal_post_content(
            post_id=post_id,
            admin_user_id=admin.id,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AdminPostNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="TREEHOLE_POST_NOT_FOUND",
            message=str(exc),
        )
    except PostSourceContentUnavailableError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="TREEHOLE_POST_CONTENT_UNAVAILABLE",
            message=str(exc),
        )

    return AdminPostRevealContentSuccessResponse(
        request_id=build_request_id(),
        data=AdminPostRevealContentData(**content_payload),
    )


@router.patch(
    "/{post_id}/visibility",
    response_model=AdminPostVisibilityUpdateSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def update_admin_post_visibility(
    post_id: int,
    payload: AdminPostVisibilityUpdateRequest,
    request: Request,
    admin: Annotated[AdminUser, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AdminPostVisibilityUpdateSuccessResponse | JSONResponse:
    """Apply one audited admin visibility action to the selected post."""
    try:
        result = AdminPostService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).update_visibility(
            post_id=post_id,
            admin_user_id=admin.id,
            action=payload.action,
            ip_address=request.client.host if request.client is not None else None,
        )
    except AdminPostNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="TREEHOLE_POST_NOT_FOUND",
            message=str(exc),
        )
    except InvalidPostVisibilityTransitionError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="TREEHOLE_POST_VISIBILITY_CONFLICT",
            message=str(exc),
        )

    return AdminPostVisibilityUpdateSuccessResponse(
        request_id=build_request_id(),
        data=AdminPostVisibilityUpdateData(
            post_id=result.post.id,
            publish_status=result.post.publish_status,
            allow_publication=result.post.allow_publication,
            action=result.action,
        ),
    )
