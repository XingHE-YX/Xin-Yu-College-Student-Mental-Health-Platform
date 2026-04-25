"""Tests for student treehole feed, posting, delete, and reaction APIs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.constants.account_enums import ConsentStatus
from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.treehole_enums import (
    AIRecommendedAction,
    PostReactionType,
    TreeholeAIStatus,
    TreeholePublishStatus,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import AIAnalysisRecord, Base, PostReaction, StudentUser, TreeholePost


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated treehole API tests."""
    return Settings(
        APP_NAME="心语树洞 API 测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_treehole_api_test_app(database_file: Path):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(build_settings(database_file))
    Base.metadata.create_all(app.state.db_engine)
    return app


def create_student_with_token(
    app,
    *,
    suffix: str,
    consent_status: ConsentStatus = ConsentStatus.GRANTED,
) -> tuple[StudentUser, str]:
    """Create one student row and issue an access token for API tests."""
    with app.state.db_session_factory() as session:
        student = StudentUser(
            phone_e164=f"+86138123456{suffix}",
            wechat_openid=f"wx-treehole-{suffix}",
            display_nickname=f"匿名同学{suffix}",
            display_avatar_seed=f"seed-{suffix}",
            college_name="计算机学院",
            class_name="2026级1班",
            consent_status=consent_status,
        )
        session.add(student)
        session.commit()
        session.refresh(student)
        token = app.state.access_token_service.issue_student_access_token(student)
        return student, token


def create_post(
    app,
    *,
    student_id: int,
    anonymous_name: str,
    anonymous_avatar_key: str,
    content_raw: str,
    content_masked: str | None,
    publish_status: TreeholePublishStatus,
    allow_publication: bool,
    published_at: datetime | None,
    deleted_at: datetime | None = None,
    risk_level: QuestionnaireRiskLevel = QuestionnaireRiskLevel.LOW,
    ai_status: TreeholeAIStatus = TreeholeAIStatus.MOCKED,
    total_reaction_count: int = 0,
) -> TreeholePost:
    """Create one treehole post row with the provided publication state."""
    with app.state.db_session_factory() as session:
        post = TreeholePost(
            student_id=student_id,
            anonymous_name=anonymous_name,
            anonymous_avatar_key=anonymous_avatar_key,
            content_raw=content_raw,
            content_masked=content_masked,
            ai_status=ai_status,
            publish_status=publish_status,
            risk_level=risk_level,
            allow_publication=allow_publication,
            hug_count=total_reaction_count,
            published_at=published_at,
            deleted_at=deleted_at,
        )
        session.add(post)
        session.commit()
        session.refresh(post)
        return post


def create_reaction(
    app,
    *,
    post_id: int,
    student_id: int,
    reaction_type: PostReactionType,
) -> PostReaction:
    """Create one preset reaction row and sync the post summary count."""
    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, post_id)
        assert post is not None
        reaction = PostReaction(
            post_id=post_id,
            student_id=student_id,
            reaction_type=reaction_type,
        )
        session.add(reaction)
        post.hug_count += 1
        session.commit()
        session.refresh(reaction)
        return reaction


def test_feed_returns_only_public_posts_with_masked_content_and_reaction_state(
    tmp_path,
) -> None:
    """Feed should exclude blocked/deleted rows and expose current reaction state."""
    app = create_treehole_api_test_app(tmp_path / "treehole-feed.db")
    viewer, viewer_token = create_student_with_token(app, suffix="001")
    author, _ = create_student_with_token(app, suffix="002")

    older_public = create_post(
        app,
        student_id=author.id,
        anonymous_name=author.display_nickname,
        anonymous_avatar_key=author.display_avatar_seed,
        content_raw="原始内容 A",
        content_masked="公开内容 A",
        publish_status=TreeholePublishStatus.PUBLISHED,
        allow_publication=True,
        published_at=datetime(2026, 4, 20, 9, 0, 0),
    )
    newer_public = create_post(
        app,
        student_id=viewer.id,
        anonymous_name=viewer.display_nickname,
        anonymous_avatar_key=viewer.display_avatar_seed,
        content_raw="原始内容 B",
        content_masked="公开内容 B",
        publish_status=TreeholePublishStatus.PUBLISHED,
        allow_publication=True,
        published_at=datetime(2026, 4, 21, 9, 0, 0),
    )
    create_post(
        app,
        student_id=author.id,
        anonymous_name=author.display_nickname,
        anonymous_avatar_key=author.display_avatar_seed,
        content_raw="原始内容 C",
        content_masked=None,
        publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
        allow_publication=False,
        published_at=None,
        risk_level=QuestionnaireRiskLevel.HIGH,
        ai_status=TreeholeAIStatus.ANALYZED,
    )
    create_post(
        app,
        student_id=author.id,
        anonymous_name=author.display_nickname,
        anonymous_avatar_key=author.display_avatar_seed,
        content_raw="原始内容 D",
        content_masked="公开内容 D",
        publish_status=TreeholePublishStatus.DELETED_BY_USER,
        allow_publication=False,
        published_at=datetime(2026, 4, 19, 8, 0, 0),
        deleted_at=datetime(2026, 4, 21, 10, 0, 0),
    )

    create_reaction(
        app,
        post_id=older_public.id,
        student_id=viewer.id,
        reaction_type=PostReactionType.HUG,
    )
    create_reaction(
        app,
        post_id=older_public.id,
        student_id=author.id,
        reaction_type=PostReactionType.LIGHT,
    )
    create_reaction(
        app,
        post_id=newer_public.id,
        student_id=viewer.id,
        reaction_type=PostReactionType.ACCOMPANY,
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/treehole/feed",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    posts = payload["data"]["posts"]
    assert [post["post_id"] for post in posts] == [newer_public.id, older_public.id]
    assert posts[0]["content"] == "公开内容 B"
    assert posts[0]["is_mine"] is True
    assert "content_raw" not in posts[0]
    assert posts[0]["total_reaction_count"] == 1
    assert {item["reaction_type"]: item for item in posts[0]["reactions"]} == {
        "hug": {
            "reaction_type": "hug",
            "label": "抱抱",
            "count": 0,
            "reacted_by_me": False,
        },
        "light": {
            "reaction_type": "light",
            "label": "点亮",
            "count": 0,
            "reacted_by_me": False,
        },
        "accompany": {
            "reaction_type": "accompany",
            "label": "陪伴",
            "count": 1,
            "reacted_by_me": True,
        },
    }

    older_reactions = {item["reaction_type"]: item for item in posts[1]["reactions"]}
    assert posts[1]["content"] == "公开内容 A"
    assert posts[1]["is_mine"] is False
    assert posts[1]["total_reaction_count"] == 2
    assert older_reactions["hug"]["count"] == 1
    assert older_reactions["hug"]["reacted_by_me"] is True
    assert older_reactions["light"]["count"] == 1
    assert older_reactions["light"]["reacted_by_me"] is False
    assert older_reactions["accompany"]["count"] == 0


def test_create_treehole_post_persists_masked_public_post_and_bootstrap_analysis(
    tmp_path,
) -> None:
    """Create should publish one bootstrap post and store a placeholder analysis row."""
    app = create_treehole_api_test_app(tmp_path / "treehole-create.db")
    _, token = create_student_with_token(app, suffix="011")
    client = TestClient(app)

    response = client.post(
        "/api/v1/treehole/posts",
        json={
            "content": "  请联系我 13812345678 或 test@example.com ，我想找人聊聊。  "
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["risk_level"] == "low"
    assert payload["data"]["publish_status"] == "published"
    assert payload["data"]["allow_publication"] is True
    assert payload["data"]["content_masked"] == "请联系我 [手机号已隐藏] 或 [邮箱已隐藏] ，我想找人聊聊。"

    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, payload["data"]["post_id"])
        assert post is not None
        assert post.content_raw == "请联系我 13812345678 或 test@example.com ，我想找人聊聊。"
        assert post.content_masked == payload["data"]["content_masked"]
        assert post.ai_status is TreeholeAIStatus.MOCKED
        assert post.publish_status is TreeholePublishStatus.PUBLISHED
        assert post.allow_publication is True
        assert post.published_at is not None

        analysis = session.scalar(
            select(AIAnalysisRecord).where(AIAnalysisRecord.target_id == post.id)
        )
        assert analysis is not None
        assert analysis.parsed_risk_level is QuestionnaireRiskLevel.LOW
        assert analysis.recommended_action is AIRecommendedAction.PUBLISH
        assert analysis.fallback_used is True


def test_create_treehole_post_rejects_students_without_granted_consent(
    tmp_path,
) -> None:
    """Students without granted crisis consent should not be able to post."""
    app = create_treehole_api_test_app(tmp_path / "treehole-consent.db")
    _, token = create_student_with_token(
        app,
        suffix="021",
        consent_status=ConsentStatus.DECLINED,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/treehole/posts",
        json={"content": "我想说点什么"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "TREEHOLE_CONSENT_REQUIRED"

    with app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TreeholePost)) == 0


def test_delete_treehole_post_soft_deletes_owner_post_and_hides_it_from_feed(
    tmp_path,
) -> None:
    """Delete should keep the row but remove it from the public treehole feed."""
    app = create_treehole_api_test_app(tmp_path / "treehole-delete.db")
    student, token = create_student_with_token(app, suffix="031")
    other_student, _ = create_student_with_token(app, suffix="032")
    deleted_post = create_post(
        app,
        student_id=student.id,
        anonymous_name=student.display_nickname,
        anonymous_avatar_key=student.display_avatar_seed,
        content_raw="原始内容待删除",
        content_masked="公开内容待删除",
        publish_status=TreeholePublishStatus.PUBLISHED,
        allow_publication=True,
        published_at=datetime(2026, 4, 22, 9, 0, 0),
    )
    kept_post = create_post(
        app,
        student_id=other_student.id,
        anonymous_name=other_student.display_nickname,
        anonymous_avatar_key=other_student.display_avatar_seed,
        content_raw="原始内容保留",
        content_masked="公开内容保留",
        publish_status=TreeholePublishStatus.PUBLISHED,
        allow_publication=True,
        published_at=datetime(2026, 4, 22, 8, 0, 0),
    )
    client = TestClient(app)

    delete_response = client.delete(
        f"/api/v1/treehole/posts/{deleted_post.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert delete_payload["data"]["post_id"] == deleted_post.id
    assert delete_payload["data"]["publish_status"] == "deleted_by_user"
    assert delete_payload["data"]["deleted_at"] is not None

    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, deleted_post.id)
        assert post is not None
        assert post.publish_status is TreeholePublishStatus.DELETED_BY_USER
        assert post.allow_publication is False
        assert post.deleted_at is not None

    feed_response = client.get(
        "/api/v1/treehole/feed",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert feed_response.status_code == 200
    posts = feed_response.json()["data"]["posts"]
    assert [post["post_id"] for post in posts] == [kept_post.id]


def test_reaction_endpoint_is_idempotent_for_duplicate_reaction_types(tmp_path) -> None:
    """Submitting the same reaction twice should not create duplicate rows or counts."""
    app = create_treehole_api_test_app(tmp_path / "treehole-reactions.db")
    author, _ = create_student_with_token(app, suffix="041")
    _, token = create_student_with_token(app, suffix="042")
    post = create_post(
        app,
        student_id=author.id,
        anonymous_name=author.display_nickname,
        anonymous_avatar_key=author.display_avatar_seed,
        content_raw="原始内容互动",
        content_masked="公开内容互动",
        publish_status=TreeholePublishStatus.PUBLISHED,
        allow_publication=True,
        published_at=datetime(2026, 4, 23, 9, 0, 0),
    )
    client = TestClient(app)

    first_response = client.post(
        f"/api/v1/treehole/posts/{post.id}/reactions",
        json={"reaction_type": "hug"},
        headers={"Authorization": f"Bearer {token}"},
    )
    duplicate_response = client.post(
        f"/api/v1/treehole/posts/{post.id}/reactions",
        json={"reaction_type": "hug"},
        headers={"Authorization": f"Bearer {token}"},
    )
    second_type_response = client.post(
        f"/api/v1/treehole/posts/{post.id}/reactions",
        json={"reaction_type": "light"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first_response.status_code == 200
    assert duplicate_response.status_code == 200
    assert second_type_response.status_code == 200
    assert first_response.json()["data"]["total_reaction_count"] == 1
    assert duplicate_response.json()["data"]["total_reaction_count"] == 1

    final_data = second_type_response.json()["data"]
    reaction_map = {item["reaction_type"]: item for item in final_data["reactions"]}
    assert final_data["total_reaction_count"] == 2
    assert reaction_map["hug"]["count"] == 1
    assert reaction_map["hug"]["reacted_by_me"] is True
    assert reaction_map["light"]["count"] == 1
    assert reaction_map["light"]["reacted_by_me"] is True
    assert reaction_map["accompany"]["count"] == 0

    with app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PostReaction)) == 2
        stored_post = session.get(TreeholePost, post.id)
        assert stored_post is not None
        assert stored_post.hug_count == 2


def test_reaction_endpoint_rejects_non_public_posts(tmp_path) -> None:
    """Reactions should fail when the target post is not publicly visible."""
    app = create_treehole_api_test_app(tmp_path / "treehole-reaction-blocked.db")
    author, _ = create_student_with_token(app, suffix="051")
    _, token = create_student_with_token(app, suffix="052")
    post = create_post(
        app,
        student_id=author.id,
        anonymous_name=author.display_nickname,
        anonymous_avatar_key=author.display_avatar_seed,
        content_raw="原始高风险内容",
        content_masked=None,
        publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
        allow_publication=False,
        published_at=None,
        risk_level=QuestionnaireRiskLevel.HIGH,
        ai_status=TreeholeAIStatus.ANALYZED,
    )
    client = TestClient(app)

    response = client.post(
        f"/api/v1/treehole/posts/{post.id}/reactions",
        json={"reaction_type": "hug"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "TREEHOLE_POST_NOT_PUBLIC"

    with app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PostReaction)) == 0
