"""Tests for administrator post-management APIs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import select

from src.constants.account_enums import AdminRoleCode, ConsentStatus, StudentRiskStatus
from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.treehole_enums import (
    AIAnalysisProvider,
    AIAnalysisTargetType,
    AIRecommendedAction,
    PostReactionType,
    TreeholeAIStatus,
    TreeholePublishStatus,
)
from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    AuditActorType,
    CaseSourceType,
    ReviewPriority,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import (
    AIAnalysisRecord,
    AdminUser,
    AlertCase,
    AuditLog,
    Base,
    PostReaction,
    StudentUser,
    TreeholePost,
)

PASSWORD_HASHER = PasswordHash.recommended()


def build_settings(database_file: Path) -> Settings:
    """Create runtime settings for isolated admin-post API tests."""
    return Settings(
        APP_NAME="心语后台帖子管理测试后端",
        APP_ENV="testing",
        API_V1_PREFIX="/api/v1",
        DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
        JWT_SECRET_KEY="jwt-test-secret",
        DEEPSEEK_API_KEY="deepseek-test-key",
        WECHAT_APP_ID="test-wechat-app-id",
        WECHAT_APP_SECRET="test-wechat-app-secret",
        ENABLE_DEMO_LOGIN=False,
    )


def create_admin_posts_test_app(database_file: Path):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(build_settings(database_file))
    Base.metadata.create_all(app.state.db_engine)
    return app


def create_admin_user(app) -> AdminUser:
    """Insert one active administrator row with a valid Argon2 password hash."""
    with app.state.db_session_factory() as session:
        admin = AdminUser(
            username="platform.admin",
            password_hash=PASSWORD_HASHER.hash("Admin#2026"),
            role_code=AdminRoleCode.PLATFORM_ADMIN,
            display_name="平台管理员",
            is_active=True,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        return admin


def seed_post_management_data(app) -> dict[str, int]:
    """Insert students, posts, reactions, AI records, and blocked alert data."""
    with app.state.db_session_factory() as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-post-admin-1",
            display_nickname="Quiet Harbor",
            display_avatar_seed="seed-harbor",
            college_name="心理学院",
            class_name="2026级1班",
            consent_status=ConsentStatus.GRANTED,
            risk_status=StudentRiskStatus.HIGH,
        )
        other_student = StudentUser(
            phone_e164="+8613812345688",
            wechat_openid="wx-post-admin-2",
            display_nickname="Soft Cedar",
            display_avatar_seed="seed-cedar",
            college_name="计算机学院",
            class_name="2026级2班",
            consent_status=ConsentStatus.GRANTED,
            risk_status=StudentRiskStatus.WATCH,
        )
        session.add_all([student, other_student])
        session.flush()

        published_post = TreeholePost(
            student_id=student.id,
            anonymous_name="匿名港湾",
            anonymous_avatar_key="harbor",
            content_raw="这是一个已公开的树洞内容。",
            content_masked="这是一个已公开的树洞内容。",
            ai_status=TreeholeAIStatus.ANALYZED,
            publish_status=TreeholePublishStatus.PUBLISHED,
            risk_level=QuestionnaireRiskLevel.LOW,
            allow_publication=True,
            hug_count=2,
            published_at=datetime(2026, 4, 26, 10, 0, 0),
        )
        newer_published_post = TreeholePost(
            student_id=other_student.id,
            anonymous_name="匿名雪松",
            anonymous_avatar_key="cedar",
            content_raw="这是另一条较新的公开内容。",
            content_masked="这是另一条较新的公开内容。",
            ai_status=TreeholeAIStatus.MOCKED,
            publish_status=TreeholePublishStatus.PUBLISHED,
            risk_level=QuestionnaireRiskLevel.WATCH,
            allow_publication=True,
            hug_count=0,
            published_at=datetime(2026, 4, 27, 11, 0, 0),
        )
        hidden_post = TreeholePost(
            student_id=student.id,
            anonymous_name="匿名回声",
            anonymous_avatar_key="echo",
            content_raw="这条内容曾公开，后来被管理员隐藏。",
            content_masked="这条内容曾公开，后来被管理员隐藏。",
            ai_status=TreeholeAIStatus.ANALYZED,
            publish_status=TreeholePublishStatus.HIDDEN_BY_ADMIN,
            risk_level=QuestionnaireRiskLevel.WATCH,
            allow_publication=False,
            hug_count=1,
            published_at=datetime(2026, 4, 24, 10, 0, 0),
        )
        blocked_post = TreeholePost(
            student_id=student.id,
            anonymous_name="匿名风暴",
            anonymous_avatar_key="storm",
            content_raw="我现在不想继续了，感觉很危险。",
            content_masked=None,
            ai_status=TreeholeAIStatus.ANALYZED,
            publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
            risk_level=QuestionnaireRiskLevel.HIGH,
            allow_publication=False,
            hug_count=0,
            published_at=None,
        )
        deleted_post = TreeholePost(
            student_id=other_student.id,
            anonymous_name="匿名雾松",
            anonymous_avatar_key="mist",
            content_raw="这条内容已被学生删除。",
            content_masked="这条内容已被学生删除。",
            ai_status=TreeholeAIStatus.MOCKED,
            publish_status=TreeholePublishStatus.DELETED_BY_USER,
            risk_level=QuestionnaireRiskLevel.LOW,
            allow_publication=False,
            hug_count=0,
            published_at=datetime(2026, 4, 20, 9, 0, 0),
            deleted_at=datetime(2026, 4, 21, 9, 30, 0),
        )
        session.add_all(
            [
                published_post,
                newer_published_post,
                hidden_post,
                blocked_post,
                deleted_post,
            ]
        )
        session.flush()

        session.add_all(
            [
                PostReaction(
                    post_id=published_post.id,
                    student_id=student.id,
                    reaction_type=PostReactionType.HUG,
                ),
                PostReaction(
                    post_id=published_post.id,
                    student_id=other_student.id,
                    reaction_type=PostReactionType.LIGHT,
                ),
                PostReaction(
                    post_id=hidden_post.id,
                    student_id=student.id,
                    reaction_type=PostReactionType.ACCOMPANY,
                ),
            ]
        )

        session.add_all(
            [
                AIAnalysisRecord(
                    target_type=AIAnalysisTargetType.TREEHOLE_POST,
                    target_id=published_post.id,
                    provider=AIAnalysisProvider.DEEPSEEK,
                    model_name="deepseek-v4-flash",
                    request_payload_json={"content": published_post.content_raw},
                    response_raw_json={"risk_level": "low"},
                    parsed_risk_level=QuestionnaireRiskLevel.LOW,
                    parsed_risk_score=Decimal("0.1800"),
                    emotion_tags_json=["fatigue"],
                    trigger_phrases_json=[],
                    reason_text="内容平稳，可以公开展示。",
                    recommended_action=AIRecommendedAction.PUBLISH,
                    fallback_used=False,
                ),
                AIAnalysisRecord(
                    target_type=AIAnalysisTargetType.TREEHOLE_POST,
                    target_id=blocked_post.id,
                    provider=AIAnalysisProvider.DEEPSEEK,
                    model_name="deepseek-v4-flash",
                    request_payload_json={"content": blocked_post.content_raw},
                    response_raw_json={"risk_level": "high"},
                    parsed_risk_level=QuestionnaireRiskLevel.HIGH,
                    parsed_risk_score=Decimal("0.9600"),
                    emotion_tags_json=["绝望"],
                    trigger_phrases_json=["不想继续了"],
                    reason_text="检测到明确高风险表达，需要继续保持隐藏。",
                    recommended_action=AIRecommendedAction.MANUAL_REVIEW_HIGH,
                    fallback_used=False,
                ),
            ]
        )

        blocked_alert = AlertCase(
            student_id=student.id,
            source_type=CaseSourceType.TREEHOLE,
            source_post_id=blocked_post.id,
            case_level=AlertCaseLevel.HIGH,
            queue_status=AlertQueueStatus.PENDING_REVIEW,
            review_priority=ReviewPriority.HIGHEST,
            ai_reason_text="树洞内容检测到明确高风险表达。",
        )
        session.add(blocked_alert)
        session.commit()
        return {
            "published_post_id": published_post.id,
            "newer_published_post_id": newer_published_post.id,
            "hidden_post_id": hidden_post.id,
            "blocked_post_id": blocked_post.id,
            "deleted_post_id": deleted_post.id,
        }


def login_admin(client: TestClient) -> str:
    """Authenticate the seeded administrator and return the bearer token."""
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"username": "platform.admin", "password": "Admin#2026"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def list_audit_logs(session) -> list[AuditLog]:
    """Return all audit logs in insertion order."""
    return list(session.scalars(select(AuditLog).order_by(AuditLog.id.asc())).all())


def test_list_posts_filters_published_and_returns_status_counts(tmp_path) -> None:
    """A05 list should filter by publish status and keep global status counters."""
    app = create_admin_posts_test_app(tmp_path / "admin-posts-list.db")
    create_admin_user(app)
    identifiers = seed_post_management_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        "/api/v1/admin/posts",
        params={"publish_status": "published"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["data"]["applied_publish_status"] == "published"
    assert [item["post_id"] for item in payload["data"]["items"]] == [
        identifiers["newer_published_post_id"],
        identifiers["published_post_id"],
    ]
    assert payload["data"]["status_counts"] == [
        {"publish_status": "published", "count": 2},
        {"publish_status": "hidden_by_admin", "count": 1},
        {"publish_status": "blocked_high_risk", "count": 1},
        {"publish_status": "deleted_by_user", "count": 1},
    ]


def test_post_detail_returns_masked_content_and_analysis(tmp_path) -> None:
    """Default post detail should stay masked while still exposing moderation context."""
    app = create_admin_posts_test_app(tmp_path / "admin-posts-detail.db")
    create_admin_user(app)
    identifiers = seed_post_management_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.get(
        f"/api/v1/admin/posts/{identifiers['blocked_post_id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    post = response.json()["data"]["post"]
    assert post["publish_status"] == "blocked_high_risk"
    assert post["content"]["full_content"] is None
    assert post["content"]["full_content_available"] is True
    assert "显式展开" in post["content"]["masked_content"]
    assert post["ai_analysis"]["parsed_risk_level"] == "high"
    assert "不想继续了" in post["ai_analysis"]["trigger_phrases"]
    assert post["alert_case_summary"]["queue_status"] == "pending_review"
    assert post["action_permissions"] == {
        "can_hide": False,
        "can_keep_hidden": True,
        "can_restore_publish": False,
    }


def test_reveal_post_content_returns_raw_text_and_writes_audit(tmp_path) -> None:
    """Explicit raw-content reveal should return `content_raw` and append one audit log."""
    app = create_admin_posts_test_app(tmp_path / "admin-posts-reveal.db")
    create_admin_user(app)
    identifiers = seed_post_management_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.post(
        f"/api/v1/admin/posts/{identifiers['blocked_post_id']}/reveal-content",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["post_id"] == identifiers["blocked_post_id"]
    assert "感觉很危险" in payload["full_content"]

    with app.state.db_session_factory() as session:
        audit_logs = list_audit_logs(session)
        assert audit_logs[-1].actor_type is AuditActorType.ADMIN
        assert audit_logs[-1].action_code == "ADMIN_REVEAL_POST_CONTENT"
        assert audit_logs[-1].target_type == "treehole_post"
        assert audit_logs[-1].target_id == identifiers["blocked_post_id"]


def test_hide_published_post_updates_visibility_and_audits(tmp_path) -> None:
    """Published posts should support an audited hide action."""
    app = create_admin_posts_test_app(tmp_path / "admin-posts-hide.db")
    create_admin_user(app)
    identifiers = seed_post_management_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.patch(
        f"/api/v1/admin/posts/{identifiers['published_post_id']}/visibility",
        json={"action": "hide"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["publish_status"] == "hidden_by_admin"
    assert payload["allow_publication"] is False

    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, identifiers["published_post_id"])
        assert post is not None
        assert post.publish_status is TreeholePublishStatus.HIDDEN_BY_ADMIN
        assert post.allow_publication is False
        audit_logs = list_audit_logs(session)
        assert audit_logs[-1].action_code == "ADMIN_HIDE_POST"
        assert audit_logs[-1].metadata_json == {
            "action": "hide",
            "previous_status": "published",
            "next_status": "hidden_by_admin",
        }


def test_restore_hidden_post_republishes_content(tmp_path) -> None:
    """Admin-hidden posts should support audited restore back to `published`."""
    app = create_admin_posts_test_app(tmp_path / "admin-posts-restore.db")
    create_admin_user(app)
    identifiers = seed_post_management_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.patch(
        f"/api/v1/admin/posts/{identifiers['hidden_post_id']}/visibility",
        json={"action": "restore_publish"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["publish_status"] == "published"
    assert payload["allow_publication"] is True

    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, identifiers["hidden_post_id"])
        assert post is not None
        assert post.publish_status is TreeholePublishStatus.PUBLISHED
        assert post.allow_publication is True
        audit_logs = list_audit_logs(session)
        assert audit_logs[-1].action_code == "ADMIN_RESTORE_POST_VISIBILITY"


def test_keep_hidden_allows_blocked_post_without_state_change(tmp_path) -> None:
    """Blocked posts should support an explicit keep-hidden decision without republishing."""
    app = create_admin_posts_test_app(tmp_path / "admin-posts-keep-hidden.db")
    create_admin_user(app)
    identifiers = seed_post_management_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.patch(
        f"/api/v1/admin/posts/{identifiers['blocked_post_id']}/visibility",
        json={"action": "keep_hidden"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["publish_status"] == "blocked_high_risk"
    assert payload["allow_publication"] is False

    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, identifiers["blocked_post_id"])
        assert post is not None
        assert post.publish_status is TreeholePublishStatus.BLOCKED_HIGH_RISK
        audit_logs = list_audit_logs(session)
        assert audit_logs[-1].action_code == "ADMIN_KEEP_POST_HIDDEN"


def test_restore_blocked_post_returns_conflict(tmp_path) -> None:
    """System-blocked high-risk posts should not be restorable from the A05 page."""
    app = create_admin_posts_test_app(tmp_path / "admin-posts-conflict.db")
    create_admin_user(app)
    identifiers = seed_post_management_data(app)
    client = TestClient(app)
    access_token = login_admin(client)

    response = client.patch(
        f"/api/v1/admin/posts/{identifiers['blocked_post_id']}/visibility",
        json={"action": "restore_publish"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "TREEHOLE_POST_VISIBILITY_CONFLICT"
