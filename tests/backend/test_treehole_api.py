"""Tests for student treehole feed, posting, delete, and reaction APIs."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.constants.account_enums import ConsentStatus, StudentRiskStatus
from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionnaireSubmissionStatus,
)
from src.constants.treehole_enums import (
    AIRecommendedAction,
    PostReactionType,
    TreeholeAIStatus,
    TreeholePublishStatus,
)
from src.constants.workflow_enums import (
    AlertCaseLevel,
    AlertQueueStatus,
    FocusListStatus,
    ReviewPriority,
)
from src.core.settings import Settings
from src.main import create_app
from src.models import (
    AIAnalysisRecord,
    AlertCase,
    Base,
    FocusListEntry,
    PostReaction,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)
from src.services.deepseek_service import (
    DEEPSEEK_MODEL_NAME,
    DeepSeekJsonCompletionResult,
)


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


def create_treehole_api_test_app(
    database_file: Path,
    *,
    deepseek_result: DeepSeekJsonCompletionResult | None = None,
    override_deepseek_service: bool = True,
    enable_mock_ai: bool = False,
    show_seeded_cases: bool = True,
):
    """Create an application backed by a temporary SQLite file."""
    app = create_app(
        Settings(
            APP_NAME="心语树洞 API 测试后端",
            APP_ENV="testing",
            API_V1_PREFIX="/api/v1",
            DATABASE_URL=f"sqlite+pysqlite:///{database_file}",
            JWT_SECRET_KEY="jwt-test-secret",
            DEEPSEEK_API_KEY="deepseek-test-key",
            WECHAT_APP_ID="test-wechat-app-id",
            WECHAT_APP_SECRET="test-wechat-app-secret",
            ENABLE_DEMO_LOGIN=False,
            ENABLE_MOCK_AI=enable_mock_ai,
            SHOW_SEEDED_CASES=show_seeded_cases,
        )
    )
    if override_deepseek_service:
        app.state.deepseek_service = FakeDeepSeekService(
            result=deepseek_result or build_mock_treehole_ai_result()
        )
    Base.metadata.create_all(app.state.db_engine)
    return app


class FakeDeepSeekService:
    """Deterministic DeepSeek stub used by treehole API tests."""

    def __init__(self, *, result: DeepSeekJsonCompletionResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def create_json_completion_with_fallback(self, **kwargs) -> DeepSeekJsonCompletionResult:
        self.calls.append(kwargs)
        return self.result


def build_mock_treehole_ai_result(
    *,
    fallback_used: bool = True,
    risk_level: str = "low",
    risk_score: str = "0.1200",
    recommended_action: str = "publish",
    emotion_tags: list[str] | None = None,
    trigger_phrases: list[str] | None = None,
    reason_text: str = "模拟回退：当前内容未出现明确高风险信号。",
) -> DeepSeekJsonCompletionResult:
    """Build one normalized fake AI result for treehole posting tests."""
    content_json = {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "emotion_tags": emotion_tags or ["fatigue"],
        "trigger_phrases": trigger_phrases or [],
        "reason_text": reason_text,
        "recommended_action": recommended_action,
    }
    return DeepSeekJsonCompletionResult(
        request_payload={
            "model": DEEPSEEK_MODEL_NAME,
            "messages": [
                {
                    "role": "system",
                    "content": "Analyze treehole safety risk.",
                },
                {
                    "role": "user",
                    "content": "fake test treehole content",
                },
            ],
            "response_format": {"type": "json_object"},
        },
        response_payload={
            "source": "mock_response.json" if fallback_used else "deepseek_api",
            "content": content_json,
        },
        completion_id=None if fallback_used else "chatcmpl-treehole-test-001",
        model_name=DEEPSEEK_MODEL_NAME,
        finish_reason="mock_fallback" if fallback_used else "stop",
        content_text=json.dumps(content_json, ensure_ascii=False),
        content_json=content_json,
        fallback_used=fallback_used,
        fallback_reason="DeepSeek chat completion timed out" if fallback_used else None,
    )


def create_student_with_token(
    app,
    *,
    suffix: str,
    consent_status: ConsentStatus = ConsentStatus.GRANTED,
    risk_status: StudentRiskStatus = StudentRiskStatus.NORMAL,
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
            risk_status=risk_status,
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


def create_questionnaire_submission(
    app,
    *,
    student_id: int,
    questionnaire_code: str,
    risk_level: QuestionnaireRiskLevel,
    hard_trigger_hit: bool,
    raw_score: int,
    standardized_score: int | None = None,
) -> QuestionnaireSubmission:
    """Create one questionnaire submission row for treehole aggregation tests."""
    with app.state.db_session_factory() as session:
        template = session.scalar(
            select(QuestionnaireTemplate).where(
                QuestionnaireTemplate.code == questionnaire_code
            )
        )
        if template is None:
            template = QuestionnaireTemplate(
                code=questionnaire_code,
                name=f"{questionnaire_code} 模板",
                category=QuestionnaireCategory.REQUIRED,
                question_count=20,
                scoring_mode=QuestionnaireScoringMode.ZUNG_STANDARD,
                unlock_required=True,
                is_active=True,
            )
            session.add(template)
            session.flush()

        submission = QuestionnaireSubmission(
            student_id=student_id,
            template_id=template.id,
            started_at=datetime(2026, 4, 24, 8, 0, 0),
            submitted_at=datetime(2026, 4, 24, 8, 20, 0),
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=raw_score,
            standardized_score=standardized_score,
            risk_level=risk_level,
            hard_trigger_hit=hard_trigger_hit,
            scoring_snapshot_json={"questionnaire_code": questionnaire_code},
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)
        return submission


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


def test_create_treehole_post_persists_masked_public_post_and_mock_fallback_analysis(
    tmp_path,
) -> None:
    """Create should keep the student flow alive by storing one fallback analysis row."""
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
        assert post.risk_level is QuestionnaireRiskLevel.LOW
        assert post.allow_publication is True
        assert post.published_at is not None

        analysis = session.scalar(
            select(AIAnalysisRecord).where(AIAnalysisRecord.target_id == post.id)
        )
        assert analysis is not None
        assert analysis.parsed_risk_level is QuestionnaireRiskLevel.LOW
        assert analysis.parsed_risk_score == Decimal("0.1200")
        assert analysis.recommended_action is AIRecommendedAction.PUBLISH
        assert analysis.fallback_used is True
        assert analysis.provider.value == "deepseek"
        assert analysis.model_name == DEEPSEEK_MODEL_NAME
        assert analysis.response_raw_json["source"] == "mock_response.json"
        student = session.get(StudentUser, post.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.NORMAL
        assert session.scalar(select(func.count()).select_from(FocusListEntry)) == 0
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 0


def test_create_treehole_post_publishes_watch_content_and_writes_focus_list_entry(
    tmp_path,
) -> None:
    """Watch-level content should stay public but enter the administrative focus list."""
    app = create_treehole_api_test_app(
        tmp_path / "treehole-create-remote.db",
        deepseek_result=build_mock_treehole_ai_result(
            fallback_used=False,
            risk_level="watch",
            risk_score="0.6400",
            recommended_action="focus_list",
            emotion_tags=["stress", "fatigue"],
            trigger_phrases=["撑不住了"],
            reason_text="检测到持续性消极和压力表达，但未出现明确自伤信号。",
        ),
    )
    _, token = create_student_with_token(app, suffix="012")
    client = TestClient(app)

    response = client.post(
        "/api/v1/treehole/posts",
        json={"content": "最近总觉得撑不住了，但我还在努力。"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["publish_status"] == "published"
    assert payload["data"]["risk_level"] == "watch"
    assert payload["data"]["allow_publication"] is True

    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, payload["data"]["post_id"])
        assert post is not None
        assert post.ai_status is TreeholeAIStatus.ANALYZED
        assert post.publish_status is TreeholePublishStatus.PUBLISHED
        assert post.risk_level is QuestionnaireRiskLevel.WATCH
        assert post.content_masked is not None
        assert post.published_at is not None

        analysis = session.scalar(
            select(AIAnalysisRecord).where(AIAnalysisRecord.target_id == post.id)
        )
        assert analysis is not None
        assert analysis.parsed_risk_level is QuestionnaireRiskLevel.WATCH
        assert analysis.parsed_risk_score == Decimal("0.6400")
        assert analysis.recommended_action is AIRecommendedAction.FOCUS_LIST
        assert analysis.fallback_used is False
        assert analysis.trigger_phrases_json == ["撑不住了"]
        focus_entry = session.scalar(select(FocusListEntry))
        assert focus_entry is not None
        assert focus_entry.student_id == post.student_id
        assert focus_entry.source_id == post.id
        assert focus_entry.reason_code == "TREEHOLE_AI_WATCH"
        assert focus_entry.status is FocusListStatus.ACTIVE
        assert "TREEHOLE_AI_WATCH" in focus_entry.reason_text
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 0
        student = session.get(StudentUser, post.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.WATCH


def test_create_treehole_post_blocks_high_risk_content_and_creates_alert_case(
    tmp_path,
) -> None:
    """High-risk content should be intercepted, not published, and queued for review."""
    app = create_treehole_api_test_app(
        tmp_path / "treehole-create-high.db",
        deepseek_result=build_mock_treehole_ai_result(
            fallback_used=False,
            risk_level="high",
            risk_score="0.9500",
            recommended_action="manual_review_high",
            emotion_tags=["despair"],
            trigger_phrases=["不想活了"],
            reason_text="检测到明确自伤或自杀意图，需要优先人工复核。",
        ),
    )
    _, token = create_student_with_token(app, suffix="013")
    client = TestClient(app)

    response = client.post(
        "/api/v1/treehole/posts",
        json={"content": "我真的不想活了，感觉没有意义。"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "safety_intercepted"
    assert payload["data"]["risk_level"] == "high"
    assert payload["data"]["publish_status"] == "blocked_high_risk"
    assert payload["data"]["allow_publication"] is False
    assert payload["data"]["content_masked"] is None
    assert payload["data"]["published_at"] is None
    assert payload["data"]["hotline"] == "400-161-9995"

    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, payload["data"]["post_id"])
        assert post is not None
        assert post.ai_status is TreeholeAIStatus.ANALYZED
        assert post.publish_status is TreeholePublishStatus.BLOCKED_HIGH_RISK
        assert post.risk_level is QuestionnaireRiskLevel.HIGH
        assert post.allow_publication is False
        assert post.content_masked is None
        assert post.published_at is None

        analysis = session.scalar(
            select(AIAnalysisRecord).where(AIAnalysisRecord.target_id == post.id)
        )
        assert analysis is not None
        assert analysis.parsed_risk_level is QuestionnaireRiskLevel.HIGH
        assert analysis.recommended_action is AIRecommendedAction.MANUAL_REVIEW_HIGH
        assert analysis.fallback_used is False

        alert_case = session.scalar(select(AlertCase))
        assert alert_case is not None
        assert alert_case.student_id == post.student_id
        assert alert_case.source_post_id == post.id
        assert alert_case.case_level is AlertCaseLevel.HIGH
        assert alert_case.queue_status is AlertQueueStatus.PENDING_REVIEW
        assert alert_case.review_priority is ReviewPriority.HIGHEST
        assert "检测到明确自伤或自杀意图" in (alert_case.ai_reason_text or "")
        assert session.scalar(select(func.count()).select_from(FocusListEntry)) == 0
        student = session.get(StudentUser, post.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.HIGH

    feed_response = client.get(
        "/api/v1/treehole/feed",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert feed_response.status_code == 200
    assert feed_response.json()["data"]["posts"] == []


def test_enable_mock_ai_blocks_high_risk_treehole_post_without_remote_http(
    monkeypatch,
    tmp_path,
) -> None:
    """Forced mock AI should still intercept high-risk content without upstream access."""
    app = create_treehole_api_test_app(
        tmp_path / "treehole-create-mock-ai.db",
        override_deepseek_service=False,
        enable_mock_ai=True,
    )
    _, token = create_student_with_token(app, suffix="015")
    client = TestClient(app)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("remote DeepSeek HTTP should not be called when mock AI is enabled")

    monkeypatch.setattr("src.services.deepseek_service.httpx.Client", fail_if_called)

    response = client.post(
        "/api/v1/treehole/posts",
        json={"content": "我真的不想活了，今晚一直在想从楼上跳下去。"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "safety_intercepted"
    assert payload["data"]["risk_level"] == "high"
    assert payload["data"]["publish_status"] == "blocked_high_risk"
    assert payload["data"]["allow_publication"] is False

    with app.state.db_session_factory() as session:
        analysis = session.scalar(select(AIAnalysisRecord))
        assert analysis is not None
        assert analysis.fallback_used is True
        assert analysis.parsed_risk_level is QuestionnaireRiskLevel.HIGH
        assert analysis.recommended_action is AIRecommendedAction.MANUAL_REVIEW_HIGH
        assert analysis.response_raw_json["mock_mode"] == "forced_enabled"
        assert analysis.response_raw_json["mock_classification"] == "high"
        assert "不想活了" in analysis.trigger_phrases_json
        alert_case = session.scalar(select(AlertCase))
        assert alert_case is not None
        assert alert_case.queue_status is AlertQueueStatus.PENDING_REVIEW


def test_create_treehole_post_does_not_block_when_only_questionnaire_history_is_high(
    tmp_path,
) -> None:
    """High-risk questionnaire history should add backend follow-up without blocking a benign post."""
    app = create_treehole_api_test_app(
        tmp_path / "treehole-questionnaire-history-high.db",
        deepseek_result=build_mock_treehole_ai_result(
            fallback_used=False,
            risk_level="low",
            risk_score="0.0200",
            recommended_action="publish",
            emotion_tags=["joy"],
            trigger_phrases=[],
            reason_text="当前文本积极稳定，未出现高风险信号。",
        ),
    )
    student, token = create_student_with_token(
        app,
        suffix="016",
        risk_status=StudentRiskStatus.HIGH,
    )
    create_questionnaire_submission(
        app,
        student_id=student.id,
        questionnaire_code="UPI",
        risk_level=QuestionnaireRiskLevel.HIGH,
        hard_trigger_hit=True,
        raw_score=2,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/treehole/posts",
        json={"content": "今天天气真好，路上遇到了一只可爱的小猫，我真开心。"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "success"
    assert payload["data"]["risk_level"] == "low"
    assert payload["data"]["publish_status"] == "published"
    assert payload["data"]["allow_publication"] is True
    assert payload["data"]["content_masked"] == "今天天气真好，路上遇到了一只可爱的小猫，我真开心。"

    with app.state.db_session_factory() as session:
        post = session.get(TreeholePost, payload["data"]["post_id"])
        assert post is not None
        assert post.risk_level is QuestionnaireRiskLevel.LOW
        assert post.publish_status is TreeholePublishStatus.PUBLISHED
        assert post.allow_publication is True

        analysis = session.scalar(
            select(AIAnalysisRecord).where(AIAnalysisRecord.target_id == post.id)
        )
        assert analysis is not None
        assert analysis.parsed_risk_level is QuestionnaireRiskLevel.LOW
        assert analysis.recommended_action is AIRecommendedAction.PUBLISH

        focus_entry = session.scalar(select(FocusListEntry))
        assert focus_entry is not None
        assert focus_entry.student_id == post.student_id
        assert focus_entry.source_id == post.id
        assert focus_entry.reason_code == "QUESTIONNAIRE_HARD_TRIGGER"
        assert "QUESTIONNAIRE_HARD_TRIGGER" in focus_entry.reason_text
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 0


def test_create_treehole_post_uses_focus_list_for_history_only_review_hint(
    tmp_path,
) -> None:
    """Historical high risk should not block publication for neutral current content."""
    app = create_treehole_api_test_app(
        tmp_path / "treehole-history-watch.db",
        deepseek_result=build_mock_treehole_ai_result(
            fallback_used=False,
            risk_level="low",
            risk_score="0.1200",
            recommended_action="publish",
            emotion_tags=["fatigue"],
            trigger_phrases=[],
            reason_text="当前文本未见明确高风险信号。",
        ),
    )
    _, token = create_student_with_token(
        app,
        suffix="014",
        risk_status=StudentRiskStatus.HIGH,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/treehole/posts",
        json={"content": "今天有点累，想找个地方说说话。"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "success"
    assert payload["data"]["risk_level"] == "low"
    assert payload["data"]["publish_status"] == "published"
    assert payload["data"]["allow_publication"] is True

    with app.state.db_session_factory() as session:
        focus_entry = session.scalar(select(FocusListEntry))
        assert focus_entry is not None
        assert focus_entry.reason_code == "HISTORY_HIGH_REVIEW"
        assert "历史高风险记录" in focus_entry.reason_text
        assert session.scalar(select(func.count()).select_from(AlertCase)) == 0
        student = session.get(StudentUser, focus_entry.student_id)
        assert student is not None
        assert student.risk_status is StudentRiskStatus.HIGH


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


def test_reaction_endpoint_toggles_same_reaction_type(tmp_path) -> None:
    """Submitting the same reaction twice should add then remove that preset reaction."""
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
    assert duplicate_response.json()["data"]["total_reaction_count"] == 0

    duplicate_map = {
        item["reaction_type"]: item for item in duplicate_response.json()["data"]["reactions"]
    }
    assert duplicate_map["hug"]["count"] == 0
    assert duplicate_map["hug"]["reacted_by_me"] is False

    final_data = second_type_response.json()["data"]
    reaction_map = {item["reaction_type"]: item for item in final_data["reactions"]}
    assert final_data["total_reaction_count"] == 1
    assert reaction_map["hug"]["count"] == 0
    assert reaction_map["hug"]["reacted_by_me"] is False
    assert reaction_map["light"]["count"] == 1
    assert reaction_map["light"]["reacted_by_me"] is True
    assert reaction_map["accompany"]["count"] == 0

    with app.state.db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PostReaction)) == 1
        stored_post = session.get(TreeholePost, post.id)
        assert stored_post is not None
        assert stored_post.hug_count == 1


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
