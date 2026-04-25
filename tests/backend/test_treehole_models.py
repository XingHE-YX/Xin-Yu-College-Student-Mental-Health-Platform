"""Tests for treehole, AI analysis, and reaction ORM models."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.constants.treehole_enums import (
    AIAnalysisProvider,
    AIAnalysisTargetType,
    AIRecommendedAction,
    PostReactionType,
    TreeholeAIStatus,
    TreeholePublishStatus,
)
from src.models import AIAnalysisRecord, Base, PostReaction, StudentUser, TreeholePost


def test_treehole_tables_compile_to_mysql_contract() -> None:
    """The treehole-related models should compile to the expected MySQL schema."""
    post_sql = str(CreateTable(TreeholePost.__table__).compile(dialect=mysql.dialect()))
    analysis_sql = str(
        CreateTable(AIAnalysisRecord.__table__).compile(dialect=mysql.dialect())
    )
    reaction_sql = str(
        CreateTable(PostReaction.__table__).compile(dialect=mysql.dialect())
    )

    assert "MEDIUMTEXT NOT NULL" in post_sql
    assert "ENUM('pending','analyzed','mocked','failed')" in post_sql
    assert (
        "ENUM('pending_review','published','blocked_high_risk','deleted_by_user','hidden_by_admin')"
        in post_sql
    )
    assert "INTEGER UNSIGNED NOT NULL" in post_sql
    assert "FOREIGN KEY(student_id) REFERENCES student_users (id)" in post_sql
    assert "ENUM('treehole_post')" in analysis_sql
    assert "ENUM('deepseek')" in analysis_sql
    assert "FOREIGN KEY(target_id) REFERENCES treehole_posts (id)" in analysis_sql
    assert "ENUM('publish','focus_list','manual_review_high')" in analysis_sql
    assert "ENUM('hug','light','accompany')" in reaction_sql
    assert "FOREIGN KEY(post_id) REFERENCES treehole_posts (id)" in reaction_sql
    assert "FOREIGN KEY(student_id) REFERENCES student_users (id)" in reaction_sql
    assert "uq_post_reactions_post_id_student_id_reaction_type" in reaction_sql


def test_treehole_tables_create_expected_constraints_and_persistence() -> None:
    """Treehole posts, AI analysis records, and reactions should persist together."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            StudentUser.__table__,
            TreeholePost.__table__,
            AIAnalysisRecord.__table__,
            PostReaction.__table__,
        ],
    )
    inspector = inspect(engine)

    treehole_foreign_keys = inspector.get_foreign_keys("treehole_posts")
    analysis_foreign_keys = inspector.get_foreign_keys("ai_analysis_records")
    reaction_foreign_keys = inspector.get_foreign_keys("post_reactions")
    reaction_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("post_reactions")
    }

    assert treehole_foreign_keys[0]["referred_table"] == "student_users"
    assert treehole_foreign_keys[0]["constrained_columns"] == ["student_id"]
    assert analysis_foreign_keys[0]["referred_table"] == "treehole_posts"
    assert analysis_foreign_keys[0]["constrained_columns"] == ["target_id"]
    assert sorted(
        foreign_key["referred_table"] for foreign_key in reaction_foreign_keys
    ) == [
        "student_users",
        "treehole_posts",
    ]
    assert ("post_id", "student_id", "reaction_type") in reaction_unique_constraints

    with Session(engine) as session:
        author = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-treehole-author",
            display_nickname="作者同学",
            display_avatar_seed="seed-author",
            college_name="心理学院",
            class_name="2026级1班",
        )
        reactor = StudentUser(
            phone_e164="+8613812345679",
            wechat_openid="wx-treehole-reactor",
            display_nickname="支持同学",
            display_avatar_seed="seed-reactor",
            college_name="计算机学院",
            class_name="2026级2班",
        )
        session.add_all([author, reactor])
        session.flush()

        pending_post = TreeholePost(
            student_id=author.id,
            anonymous_name="匿名树洞 01",
            anonymous_avatar_key="leaf-01",
            content_raw="今天有点累，想安静一下。",
        )
        published_post = TreeholePost(
            student_id=author.id,
            anonymous_name="匿名树洞 02",
            anonymous_avatar_key="leaf-02",
            content_raw="最近压力有点大，但还想坚持下去。",
            content_masked="最近压力有点大，但还想坚持下去。",
            ai_status=TreeholeAIStatus.ANALYZED,
            publish_status=TreeholePublishStatus.PUBLISHED,
            risk_level=QuestionnaireRiskLevel.WATCH,
            allow_publication=True,
            hug_count=1,
            published_at=author.created_at,
        )
        session.add_all([pending_post, published_post])
        session.flush()

        analysis_record = AIAnalysisRecord(
            target_type=AIAnalysisTargetType.TREEHOLE_POST,
            target_id=published_post.id,
            provider=AIAnalysisProvider.DEEPSEEK,
            model_name="deepseek-chat",
            request_payload_json={"content": published_post.content_raw},
            response_raw_json={"risk_level": "watch", "score": "0.8123"},
            parsed_risk_level=QuestionnaireRiskLevel.WATCH,
            parsed_risk_score=Decimal("0.8123"),
            emotion_tags_json=["stress", "fatigue"],
            trigger_phrases_json=["压力有点大"],
            reason_text="检测到持续压力表达，但未出现明确高风险短语。",
            recommended_action=AIRecommendedAction.FOCUS_LIST,
            fallback_used=False,
        )
        reaction = PostReaction(
            post_id=published_post.id,
            student_id=reactor.id,
            reaction_type=PostReactionType.HUG,
        )
        session.add_all([analysis_record, reaction])
        session.flush()
        session.refresh(author)
        session.refresh(pending_post)
        session.refresh(published_post)
        session.refresh(reactor)

        assert pending_post.ai_status is TreeholeAIStatus.PENDING
        assert pending_post.publish_status is TreeholePublishStatus.PENDING_REVIEW
        assert pending_post.risk_level is QuestionnaireRiskLevel.LOW
        assert pending_post.allow_publication is False
        assert pending_post.hug_count == 0
        assert published_post.id is not None
        assert published_post.student.id == author.id
        assert published_post.ai_analysis_records[0].id == analysis_record.id
        assert published_post.reactions[0].id == reaction.id
        assert analysis_record.post.id == published_post.id
        assert analysis_record.parsed_risk_score == Decimal("0.8123")
        assert reaction.student.id == reactor.id
        assert len(author.treehole_posts) == 2
        assert reactor.post_reactions[0].id == reaction.id

    engine.dispose()
