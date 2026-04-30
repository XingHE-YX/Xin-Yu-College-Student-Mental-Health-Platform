"""Student treehole feed, posting, delete, and reaction routes."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.constants.treehole_enums import TreeholePublishStatus
from src.core.auth import get_current_student
from src.core.database import get_db_session
from src.models.student_user import StudentUser
from src.schemas.treehole import (
    TreeholeCreatePostData,
    TreeholeCreatePostRequest,
    TreeholeCreatePostSuccessResponse,
    TreeholeDeletePostData,
    TreeholeDeletePostSuccessResponse,
    TreeholeFeedData,
    TreeholeFeedPostResponse,
    TreeholeFeedSuccessResponse,
    TreeholeReactionData,
    TreeholeReactionRequest,
    TreeholeReactionResponse,
    TreeholeReactionSuccessResponse,
)
from src.services.treehole_service import (
    TREEHOLE_HOTLINE_PHONE,
    TreeholeAIAnalysisError,
    TreeholeConsentRequiredError,
    TreeholeContentEmptyError,
    TreeholeFeedPostSnapshot,
    TreeholePostNotFoundError,
    TreeholePostNotPublicError,
    TreeholeReactionSnapshot,
    TreeholeService,
)

router = APIRouter(prefix="/treehole", tags=["treehole"])

REACTION_LABELS = {
    "hug": "抱抱",
    "light": "点亮",
    "accompany": "陪伴",
}


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


def build_reaction_response(
    reaction: TreeholeReactionSnapshot,
) -> TreeholeReactionResponse:
    """Serialize one reaction snapshot into the API response shape."""
    return TreeholeReactionResponse(
        reaction_type=reaction.reaction_type,
        label=REACTION_LABELS[reaction.reaction_type.value],
        count=reaction.count,
        reacted_by_me=reaction.reacted_by_me,
    )


def build_feed_post_response(
    post: TreeholeFeedPostSnapshot,
) -> TreeholeFeedPostResponse:
    """Serialize one feed snapshot into the API response shape."""
    return TreeholeFeedPostResponse(
        post_id=post.post_id,
        anonymous_name=post.anonymous_name,
        anonymous_avatar_key=post.anonymous_avatar_key,
        content=post.content,
        published_at=post.published_at,
        is_mine=post.is_mine,
        total_reaction_count=post.total_reaction_count,
        reactions=[build_reaction_response(reaction) for reaction in post.reactions],
    )


@router.get(
    "/feed",
    response_model=TreeholeFeedSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def get_treehole_feed(
    request: Request,
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> TreeholeFeedSuccessResponse:
    """Return public treehole posts for the authenticated student."""
    posts = TreeholeService(
        session,
        show_seeded_cases=request.app.state.settings.show_seeded_cases,
    ).list_feed(student_id=student.id, limit=limit)
    return TreeholeFeedSuccessResponse(
        request_id=build_request_id(),
        data=TreeholeFeedData(
            posts=[build_feed_post_response(post) for post in posts],
        ),
    )


@router.post(
    "/posts",
    response_model=TreeholeCreatePostSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def create_treehole_post(
    payload: TreeholeCreatePostRequest,
    request: Request,
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> TreeholeCreatePostSuccessResponse | JSONResponse:
    """Create one new treehole post using the phase-9 publication decision rules."""
    try:
        result = TreeholeService(
            session,
            deepseek_service=request.app.state.deepseek_service,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).create_post(
            student=student,
            content=payload.content,
        )
    except TreeholeConsentRequiredError as exc:
        return build_error_response(
            http_status=status.HTTP_403_FORBIDDEN,
            code="TREEHOLE_CONSENT_REQUIRED",
            message=str(exc),
        )
    except TreeholeContentEmptyError as exc:
        return build_error_response(
            http_status=status.HTTP_400_BAD_REQUEST,
            code="TREEHOLE_CONTENT_EMPTY",
            message=str(exc),
        )
    except TreeholeAIAnalysisError as exc:
        return build_error_response(
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="TREEHOLE_AI_UNAVAILABLE",
            message=str(exc),
        )

    is_high_risk_intercept = (
        result.post.publish_status is TreeholePublishStatus.BLOCKED_HIGH_RISK
    )
    return TreeholeCreatePostSuccessResponse(
        message="safety_intercepted" if is_high_risk_intercept else "success",
        request_id=build_request_id(),
        data=TreeholeCreatePostData(
            post_id=result.post.id,
            risk_level=result.post.risk_level,
            publish_status=result.post.publish_status,
            allow_publication=result.post.allow_publication,
            anonymous_name=result.post.anonymous_name,
            anonymous_avatar_key=result.post.anonymous_avatar_key,
            content_masked=result.post.content_masked,
            published_at=result.post.published_at,
            hotline=TREEHOLE_HOTLINE_PHONE if is_high_risk_intercept else None,
        ),
    )


@router.delete(
    "/posts/{post_id}",
    response_model=TreeholeDeletePostSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def delete_treehole_post(
    post_id: int,
    request: Request,
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> TreeholeDeletePostSuccessResponse | JSONResponse:
    """Soft-delete one owned treehole post for the authenticated student."""
    try:
        post = TreeholeService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).delete_post(
            student_id=student.id,
            post_id=post_id,
        )
    except TreeholePostNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="TREEHOLE_POST_NOT_FOUND",
            message=str(exc),
        )

    return TreeholeDeletePostSuccessResponse(
        request_id=build_request_id(),
        data=TreeholeDeletePostData(
            post_id=post.id,
            publish_status=post.publish_status,
            deleted_at=post.deleted_at,
        ),
    )


@router.post(
    "/posts/{post_id}/reactions",
    response_model=TreeholeReactionSuccessResponse,
    status_code=status.HTTP_200_OK,
)
def react_to_treehole_post(
    post_id: int,
    payload: TreeholeReactionRequest,
    request: Request,
    student: Annotated[StudentUser, Depends(get_current_student)],
    session: Annotated[Session, Depends(get_db_session)],
) -> TreeholeReactionSuccessResponse | JSONResponse:
    """Submit one preset support reaction on a published treehole post."""
    try:
        result = TreeholeService(
            session,
            show_seeded_cases=request.app.state.settings.show_seeded_cases,
        ).submit_reaction(
            student_id=student.id,
            post_id=post_id,
            reaction_type=payload.reaction_type,
        )
    except TreeholePostNotFoundError as exc:
        return build_error_response(
            http_status=status.HTTP_404_NOT_FOUND,
            code="TREEHOLE_POST_NOT_FOUND",
            message=str(exc),
        )
    except TreeholePostNotPublicError as exc:
        return build_error_response(
            http_status=status.HTTP_409_CONFLICT,
            code="TREEHOLE_POST_NOT_PUBLIC",
            message=str(exc),
        )

    return TreeholeReactionSuccessResponse(
        request_id=build_request_id(),
        data=TreeholeReactionData(
            post_id=result.post_id,
            reaction_type=result.reaction_type,
            total_reaction_count=result.total_reaction_count,
            reactions=[build_reaction_response(reaction) for reaction in result.reactions],
        ),
    )
