"""Service for seeding deterministic demo data used in the defense rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.constants.account_enums import (
    AdminRoleCode,
    ConsentStatus,
    ConsentType,
    StudentRiskStatus,
)
from src.constants.questionnaire_enums import (
    QuestionnaireRiskLevel,
    QuestionnaireSubmissionStatus,
)
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
    FocusListStatus,
    InterventionActionType,
    ReviewPriority,
)
from src.models import (
    AdminUser,
    AIAnalysisRecord,
    AlertCase,
    AssessmentReport,
    AuditLog,
    ConsentRecord,
    FocusListEntry,
    InterventionLog,
    PostReaction,
    QuestionnaireAnswer,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
    TreeholePost,
)
from src.models.base import utc_now
from src.services.question_bank_seed_service import (
    QuestionBankImportSummary,
    QuestionBankSeedService,
)
from src.utils.validate_question_bank_seeds import (
    DEFAULT_SEED_DIRECTORY,
    discover_seed_files,
)

PASSWORD_HASHER = PasswordHash.recommended()
DEMO_ADMIN_USERNAME = "platform.admin"
DEMO_ADMIN_PASSWORD = "Admin#2026"
DEMO_ADMIN_DISPLAY_NAME = "平台管理员"
DEMO_AUDIT_IP_ADDRESS = "demo-seed"
DEMO_STUDENT_OPENIDS = (
    "demo-low-risk-openid",
    "demo-watch-risk-openid",
    "demo-high-risk-openid",
)
QUESTIONNAIRE_CODES = ("SCREEN", "SDS", "SAS", "SLEEP", "UPI")


@dataclass(frozen=True, slots=True)
class DemoSeedSummary:
    """Compact result returned after one demo seed run."""

    admin_created: bool
    admin_username: str
    consent_records_seeded: int
    questionnaire_submissions_seeded: int
    students_seeded: int
    posts_seeded: int
    reactions_seeded: int
    alerts_seeded: int
    focus_entries_seeded: int
    intervention_logs_seeded: int
    audit_logs_seeded: int
    question_bank_import: QuestionBankImportSummary


class DemoSeedService:
    """Populate one deterministic data slice that the admin workspace can demo."""

    def __init__(
        self,
        session: Session,
        *,
        now: datetime | None = None,
        seed_directory: Path = DEFAULT_SEED_DIRECTORY,
    ) -> None:
        self.session = session
        self.now = now or utc_now()
        self.seed_directory = seed_directory

    def seed_demo_dataset(self) -> DemoSeedSummary:
        """Import questionnaires and seed three deterministic demo students."""
        question_bank_import = self._import_question_bank()
        admin_user, admin_created = self._ensure_admin_user()
        self._clear_existing_demo_dataset()

        template_by_code = self._load_templates()
        students = self._create_students()
        consent_records = self._create_consent_records(students)
        submissions = self._create_questionnaire_submissions(
            students=students,
            template_by_code=template_by_code,
        )
        posts = self._create_treehole_posts(students)
        reactions = self._create_post_reactions(students=students, posts=posts)
        self._create_ai_analysis_records(posts)
        alerts = self._create_alert_cases(
            admin_user=admin_user,
            students=students,
            submissions=submissions,
            posts=posts,
        )
        focus_entries = self._create_focus_entries(
            students=students,
            submissions=submissions,
            posts=posts,
        )
        intervention_logs = self._create_intervention_logs(
            admin_user=admin_user,
            alerts=alerts,
        )
        audit_logs = self._create_audit_logs(
            admin_user=admin_user,
            alerts=alerts,
            posts=posts,
        )

        self.session.commit()
        return DemoSeedSummary(
            admin_created=admin_created,
            admin_username=admin_user.username,
            consent_records_seeded=len(consent_records),
            questionnaire_submissions_seeded=len(submissions),
            students_seeded=len(students),
            posts_seeded=len(posts),
            reactions_seeded=len(reactions),
            alerts_seeded=len(alerts),
            focus_entries_seeded=len(focus_entries),
            intervention_logs_seeded=len(intervention_logs),
            audit_logs_seeded=len(audit_logs),
            question_bank_import=question_bank_import,
        )

    def _import_question_bank(self) -> QuestionBankImportSummary:
        """Ensure questionnaire templates and question-bank rows exist first."""
        seed_paths = discover_seed_files(self.seed_directory)
        if not seed_paths:
            raise ValueError(
                f"no questionnaire seed JSON files found under {self.seed_directory}"
            )
        return QuestionBankSeedService(self.session).import_seed_files(seed_paths)

    def _ensure_admin_user(self) -> tuple[AdminUser, bool]:
        """Create the default demo admin only when the username does not exist."""
        admin_user = self.session.scalar(
            select(AdminUser).where(AdminUser.username == DEMO_ADMIN_USERNAME)
        )
        if admin_user is not None:
            return admin_user, False

        admin_user = AdminUser(
            username=DEMO_ADMIN_USERNAME,
            password_hash=PASSWORD_HASHER.hash(DEMO_ADMIN_PASSWORD),
            role_code=AdminRoleCode.PLATFORM_ADMIN,
            display_name=DEMO_ADMIN_DISPLAY_NAME,
            is_active=True,
        )
        self.session.add(admin_user)
        self.session.flush()
        return admin_user, True

    def _clear_existing_demo_dataset(self) -> None:
        """Remove previous demo students and their dependent records before reseeding."""
        demo_students = list(
            self.session.scalars(
                select(StudentUser).where(StudentUser.wechat_openid.in_(DEMO_STUDENT_OPENIDS))
            ).all()
        )
        self.session.execute(
            delete(AuditLog).where(AuditLog.ip_address == DEMO_AUDIT_IP_ADDRESS)
        )
        if not demo_students:
            self.session.flush()
            return

        student_ids = [student.id for student in demo_students]
        post_ids = list(
            self.session.scalars(
                select(TreeholePost.id).where(TreeholePost.student_id.in_(student_ids))
            ).all()
        )
        submission_ids = list(
            self.session.scalars(
                select(QuestionnaireSubmission.id).where(
                    QuestionnaireSubmission.student_id.in_(student_ids)
                )
            ).all()
        )
        alert_ids = list(
            self.session.scalars(
                select(AlertCase.id).where(AlertCase.student_id.in_(student_ids))
            ).all()
        )

        if post_ids:
            self.session.execute(
                delete(PostReaction).where(
                    PostReaction.post_id.in_(post_ids) | PostReaction.student_id.in_(student_ids)
                )
            )
            self.session.execute(
                delete(AIAnalysisRecord).where(AIAnalysisRecord.target_id.in_(post_ids))
            )
        if alert_ids:
            self.session.execute(
                delete(InterventionLog).where(InterventionLog.alert_case_id.in_(alert_ids))
            )
        self.session.execute(
            delete(FocusListEntry).where(FocusListEntry.student_id.in_(student_ids))
        )
        if alert_ids:
            self.session.execute(delete(AlertCase).where(AlertCase.id.in_(alert_ids)))
        self.session.execute(
            delete(AssessmentReport).where(AssessmentReport.student_id.in_(student_ids))
        )
        if submission_ids:
            self.session.execute(
                delete(QuestionnaireAnswer).where(
                    QuestionnaireAnswer.submission_id.in_(submission_ids)
                )
            )
        self.session.execute(
            delete(QuestionnaireSubmission).where(
                QuestionnaireSubmission.student_id.in_(student_ids)
            )
        )
        self.session.execute(
            delete(ConsentRecord).where(ConsentRecord.student_id.in_(student_ids))
        )
        self.session.execute(
            delete(TreeholePost).where(TreeholePost.student_id.in_(student_ids))
        )
        self.session.execute(delete(StudentUser).where(StudentUser.id.in_(student_ids)))
        self.session.flush()

    def _load_templates(self) -> dict[str, QuestionnaireTemplate]:
        """Return the questionnaire templates required by the demo submissions."""
        templates = list(
            self.session.scalars(
                select(QuestionnaireTemplate).where(
                    QuestionnaireTemplate.code.in_(QUESTIONNAIRE_CODES)
                )
            ).all()
        )
        template_by_code = {template.code: template for template in templates}
        missing_codes = [code for code in QUESTIONNAIRE_CODES if code not in template_by_code]
        if missing_codes:
            missing_text = ", ".join(missing_codes)
            raise ValueError(f"missing questionnaire templates after import: {missing_text}")
        return template_by_code

    def _create_students(self) -> dict[str, StudentUser]:
        """Create the fixed low/watch/high demo student accounts."""
        students = {
            "low": StudentUser(
                phone_e164="+8613800001001",
                wechat_openid="demo-low-risk-openid",
                display_nickname="平和银杏",
                display_avatar_seed="seed-ginkgo",
                college_name="心理学院",
                class_name="2026级应用心理1班",
                consent_status=ConsentStatus.GRANTED,
                risk_status=StudentRiskStatus.NORMAL,
                is_demo=True,
                last_login_at=self._at(days_ago=1, hour=9, minute=20),
                created_at=self._at(days_ago=20, hour=10, minute=0),
                updated_at=self._at(days_ago=1, hour=9, minute=20),
            ),
            "watch": StudentUser(
                phone_e164="+8613800001002",
                wechat_openid="demo-watch-risk-openid",
                display_nickname="微澜雪松",
                display_avatar_seed="seed-cedar",
                college_name="教育学院",
                class_name="2026级教育学2班",
                consent_status=ConsentStatus.GRANTED,
                risk_status=StudentRiskStatus.WATCH,
                is_demo=True,
                last_login_at=self._at(days_ago=0, hour=8, minute=50),
                created_at=self._at(days_ago=18, hour=10, minute=0),
                updated_at=self._at(days_ago=0, hour=8, minute=50),
            ),
            "high": StudentUser(
                phone_e164="+8613800001003",
                wechat_openid="demo-high-risk-openid",
                display_nickname="静海港湾",
                display_avatar_seed="seed-harbor",
                college_name="计算机学院",
                class_name="2026级软件工程3班",
                consent_status=ConsentStatus.GRANTED,
                risk_status=StudentRiskStatus.HIGH,
                is_demo=True,
                last_login_at=self._at(days_ago=0, hour=10, minute=35),
                created_at=self._at(days_ago=16, hour=10, minute=0),
                updated_at=self._at(days_ago=0, hour=10, minute=35),
            ),
        }
        self.session.add_all(students.values())
        self.session.flush()
        return students

    def _create_consent_records(
        self,
        students: dict[str, StudentUser],
    ) -> list[ConsentRecord]:
        """Create immutable privacy and crisis-intervention consent rows."""
        records: list[ConsentRecord] = []
        for index, student in enumerate(students.values(), start=1):
            granted_at = self._at(days_ago=14 - index, hour=9, minute=0)
            records.extend(
                [
                    ConsentRecord(
                        student_id=student.id,
                        consent_type=ConsentType.PRIVACY_POLICY,
                        consent_version="v1.0",
                        granted=True,
                        granted_at=granted_at,
                        ip_address=DEMO_AUDIT_IP_ADDRESS,
                        user_agent="demo-seed-script",
                    ),
                    ConsentRecord(
                        student_id=student.id,
                        consent_type=ConsentType.CRISIS_INTERVENTION_AUTHORIZATION,
                        consent_version="v1.0",
                        granted=True,
                        granted_at=granted_at,
                        ip_address=DEMO_AUDIT_IP_ADDRESS,
                        user_agent="demo-seed-script",
                    ),
                ]
            )
        self.session.add_all(records)
        self.session.flush()
        return records

    def _create_questionnaire_submissions(
        self,
        *,
        students: dict[str, StudentUser],
        template_by_code: dict[str, QuestionnaireTemplate],
    ) -> dict[str, QuestionnaireSubmission]:
        """Create a recent history of deterministic questionnaire submissions."""
        submissions = {
            "low_screen": self._build_submission(
                student_id=students["low"].id,
                template=template_by_code["SCREEN"],
                started_at=self._at(days_ago=6, hour=9, minute=0),
                submitted_at=self._at(days_ago=6, hour=9, minute=18),
                raw_score=26,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.LOW,
                hard_trigger_hit=False,
            ),
            "low_sds": self._build_submission(
                student_id=students["low"].id,
                template=template_by_code["SDS"],
                started_at=self._at(days_ago=5, hour=9, minute=30),
                submitted_at=self._at(days_ago=5, hour=9, minute=56),
                raw_score=41,
                standardized_score=51,
                risk_level=QuestionnaireRiskLevel.LOW,
                hard_trigger_hit=False,
            ),
            "low_sas": self._build_submission(
                student_id=students["low"].id,
                template=template_by_code["SAS"],
                started_at=self._at(days_ago=4, hour=10, minute=0),
                submitted_at=self._at(days_ago=4, hour=10, minute=22),
                raw_score=38,
                standardized_score=48,
                risk_level=QuestionnaireRiskLevel.LOW,
                hard_trigger_hit=False,
            ),
            "low_sleep": self._build_submission(
                student_id=students["low"].id,
                template=template_by_code["SLEEP"],
                started_at=self._at(days_ago=3, hour=21, minute=0),
                submitted_at=self._at(days_ago=3, hour=21, minute=12),
                raw_score=7,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.LOW,
                hard_trigger_hit=False,
            ),
            "watch_screen": self._build_submission(
                student_id=students["watch"].id,
                template=template_by_code["SCREEN"],
                started_at=self._at(days_ago=2, hour=11, minute=10),
                submitted_at=self._at(days_ago=2, hour=11, minute=28),
                raw_score=40,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.WATCH,
                hard_trigger_hit=False,
            ),
            "watch_sas": self._build_submission(
                student_id=students["watch"].id,
                template=template_by_code["SAS"],
                started_at=self._at(days_ago=1, hour=14, minute=0),
                submitted_at=self._at(days_ago=1, hour=14, minute=24),
                raw_score=46,
                standardized_score=58,
                risk_level=QuestionnaireRiskLevel.WATCH,
                hard_trigger_hit=False,
            ),
            "high_sds": self._build_submission(
                student_id=students["high"].id,
                template=template_by_code["SDS"],
                started_at=self._at(days_ago=0, hour=9, minute=40),
                submitted_at=self._at(days_ago=0, hour=10, minute=5),
                raw_score=58,
                standardized_score=73,
                risk_level=QuestionnaireRiskLevel.HIGH,
                hard_trigger_hit=True,
                hard_trigger_matches=[
                    {
                        "reason_code": "HT-02",
                        "question_code": "SDS_15",
                        "matched_value": 4,
                    }
                ],
            ),
            "high_upi": self._build_submission(
                student_id=students["high"].id,
                template=template_by_code["UPI"],
                started_at=self._at(days_ago=0, hour=10, minute=12),
                submitted_at=self._at(days_ago=0, hour=10, minute=14),
                raw_score=1,
                standardized_score=None,
                risk_level=QuestionnaireRiskLevel.HIGH,
                hard_trigger_hit=True,
                hard_trigger_matches=[
                    {
                        "reason_code": "HT-04",
                        "question_code": "UPI_01",
                        "matched_value": "yes",
                    }
                ],
            ),
        }
        self.session.add_all(submissions.values())
        self.session.flush()
        return submissions

    def _build_submission(
        self,
        *,
        student_id: int,
        template: QuestionnaireTemplate,
        started_at: datetime,
        submitted_at: datetime,
        raw_score: int,
        standardized_score: int | None,
        risk_level: QuestionnaireRiskLevel,
        hard_trigger_hit: bool,
        hard_trigger_matches: list[dict[str, object]] | None = None,
    ) -> QuestionnaireSubmission:
        """Return one deterministic questionnaire submission row."""
        return QuestionnaireSubmission(
            student_id=student_id,
            template_id=template.id,
            started_at=started_at,
            submitted_at=submitted_at,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=raw_score,
            standardized_score=standardized_score,
            risk_level=risk_level,
            hard_trigger_hit=hard_trigger_hit,
            scoring_snapshot_json={
                "questionnaire_code": template.code,
                "questionnaire_name": template.name,
                "raw_score": raw_score,
                "standardized_score": standardized_score,
                "risk_level": risk_level.value,
                "hard_trigger_hit": hard_trigger_hit,
                "hard_trigger_matches": hard_trigger_matches or [],
            },
            created_at=submitted_at,
        )

    def _create_treehole_posts(
        self,
        students: dict[str, StudentUser],
    ) -> dict[str, TreeholePost]:
        """Create three posts that cover public, hidden, and blocked states."""
        posts = {
            "low_published": TreeholePost(
                student_id=students["low"].id,
                anonymous_name="匿名银杏",
                anonymous_avatar_key="ginkgo",
                content_raw="今天去操场走了一圈，情绪比昨天稳很多，也愿意继续按时吃饭。",
                content_masked="今天去操场走了一圈，情绪比昨天稳很多，也愿意继续按时吃饭。",
                ai_status=TreeholeAIStatus.ANALYZED,
                publish_status=TreeholePublishStatus.PUBLISHED,
                risk_level=QuestionnaireRiskLevel.LOW,
                allow_publication=True,
                hug_count=2,
                published_at=self._at(days_ago=2, hour=20, minute=30),
                created_at=self._at(days_ago=2, hour=20, minute=25),
                updated_at=self._at(days_ago=2, hour=20, minute=30),
            ),
            "watch_hidden": TreeholePost(
                student_id=students["watch"].id,
                anonymous_name="匿名雪松",
                anonymous_avatar_key="cedar",
                content_raw="最近总觉得胸口发闷，回宿舍后常常想把自己关起来，不太想跟人说话。",
                content_masked="最近总觉得胸口发闷，回宿舍后常常想把自己关起来，不太想跟人说话。",
                ai_status=TreeholeAIStatus.ANALYZED,
                publish_status=TreeholePublishStatus.HIDDEN_BY_ADMIN,
                risk_level=QuestionnaireRiskLevel.WATCH,
                allow_publication=False,
                hug_count=1,
                published_at=self._at(days_ago=1, hour=20, minute=10),
                created_at=self._at(days_ago=1, hour=19, minute=58),
                updated_at=self._at(days_ago=1, hour=20, minute=18),
            ),
            "high_blocked": TreeholePost(
                student_id=students["high"].id,
                anonymous_name="匿名港湾",
                anonymous_avatar_key="harbor",
                content_raw="我真的撑不住了，今晚一直在想如果从楼顶跳下去是不是就能结束这一切。",
                content_masked=None,
                ai_status=TreeholeAIStatus.ANALYZED,
                publish_status=TreeholePublishStatus.BLOCKED_HIGH_RISK,
                risk_level=QuestionnaireRiskLevel.HIGH,
                allow_publication=False,
                hug_count=0,
                published_at=None,
                created_at=self._at(days_ago=0, hour=11, minute=5),
                updated_at=self._at(days_ago=0, hour=11, minute=5),
            ),
        }
        self.session.add_all(posts.values())
        self.session.flush()
        return posts

    def _create_post_reactions(
        self,
        *,
        students: dict[str, StudentUser],
        posts: dict[str, TreeholePost],
    ) -> list[PostReaction]:
        """Create a few preset support reactions for the demo post details."""
        reactions = [
            PostReaction(
                post_id=posts["low_published"].id,
                student_id=students["watch"].id,
                reaction_type=PostReactionType.HUG,
                created_at=self._at(days_ago=2, hour=20, minute=40),
            ),
            PostReaction(
                post_id=posts["low_published"].id,
                student_id=students["high"].id,
                reaction_type=PostReactionType.ACCOMPANY,
                created_at=self._at(days_ago=2, hour=20, minute=42),
            ),
            PostReaction(
                post_id=posts["watch_hidden"].id,
                student_id=students["low"].id,
                reaction_type=PostReactionType.LIGHT,
                created_at=self._at(days_ago=1, hour=20, minute=12),
            ),
        ]
        self.session.add_all(reactions)
        self.session.flush()
        return reactions

    def _create_ai_analysis_records(self, posts: dict[str, TreeholePost]) -> None:
        """Create one AI analysis row per seeded treehole post."""
        analysis_records = [
            AIAnalysisRecord(
                target_type=AIAnalysisTargetType.TREEHOLE_POST,
                target_id=posts["low_published"].id,
                provider=AIAnalysisProvider.DEEPSEEK,
                model_name="deepseek-chat",
                request_payload_json={
                    "content": posts["low_published"].content_raw,
                },
                response_raw_json={"risk_level": "low"},
                parsed_risk_level=QuestionnaireRiskLevel.LOW,
                parsed_risk_score=Decimal("0.1200"),
                emotion_tags_json=["放松", "恢复"],
                trigger_phrases_json=[],
                reason_text="内容整体平稳，适合公开展示在匿名广场。",
                recommended_action=AIRecommendedAction.PUBLISH,
                fallback_used=False,
                created_at=self._at(days_ago=2, hour=20, minute=29),
            ),
            AIAnalysisRecord(
                target_type=AIAnalysisTargetType.TREEHOLE_POST,
                target_id=posts["watch_hidden"].id,
                provider=AIAnalysisProvider.DEEPSEEK,
                model_name="deepseek-chat",
                request_payload_json={
                    "content": posts["watch_hidden"].content_raw,
                },
                response_raw_json={"risk_level": "watch"},
                parsed_risk_level=QuestionnaireRiskLevel.WATCH,
                parsed_risk_score=Decimal("0.6400"),
                emotion_tags_json=["压抑", "退缩"],
                trigger_phrases_json=["把自己关起来"],
                reason_text="内容显示明显的社交退缩和持续压抑，建议纳入重点观察。",
                recommended_action=AIRecommendedAction.FOCUS_LIST,
                fallback_used=False,
                created_at=self._at(days_ago=1, hour=20, minute=5),
            ),
            AIAnalysisRecord(
                target_type=AIAnalysisTargetType.TREEHOLE_POST,
                target_id=posts["high_blocked"].id,
                provider=AIAnalysisProvider.DEEPSEEK,
                model_name="deepseek-chat",
                request_payload_json={
                    "content": posts["high_blocked"].content_raw,
                },
                response_raw_json={"risk_level": "high"},
                parsed_risk_level=QuestionnaireRiskLevel.HIGH,
                parsed_risk_score=Decimal("0.9700"),
                emotion_tags_json=["绝望", "冲动"],
                trigger_phrases_json=["跳下去", "结束这一切"],
                reason_text="出现明确自伤意念与具体危险场景，必须拦截并转人工复核。",
                recommended_action=AIRecommendedAction.MANUAL_REVIEW_HIGH,
                fallback_used=False,
                created_at=self._at(days_ago=0, hour=11, minute=6),
            ),
        ]
        self.session.add_all(analysis_records)
        self.session.flush()

    def _create_alert_cases(
        self,
        *,
        admin_user: AdminUser,
        students: dict[str, StudentUser],
        submissions: dict[str, QuestionnaireSubmission],
        posts: dict[str, TreeholePost],
    ) -> dict[str, AlertCase]:
        """Create one confirmed follow-up case and one pending high-risk case."""
        alerts = {
            "watch_assessment": AlertCase(
                student_id=students["watch"].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_submission_id=submissions["watch_sas"].id,
                case_level=AlertCaseLevel.WATCH,
                queue_status=AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
                review_priority=ReviewPriority.URGENT,
                ai_reason_text="SAS 标准分偏高，且最近 48 小时情绪波动明显，需要继续跟进。",
                review_note="已联系辅导员，暂列需持续回访。",
                reviewed_by=admin_user.id,
                reviewed_at=self._at(days_ago=1, hour=21, minute=0),
                simulated_notice_log=(
                    "2026-04-29 21:10 已模拟通知辅导员值班手机，要求明早回访。"
                ),
                created_at=self._at(days_ago=1, hour=20, minute=45),
                updated_at=self._at(days_ago=0, hour=8, minute=30),
            ),
            "high_treehole": AlertCase(
                student_id=students["high"].id,
                source_type=CaseSourceType.TREEHOLE,
                source_post_id=posts["high_blocked"].id,
                case_level=AlertCaseLevel.HIGH,
                queue_status=AlertQueueStatus.PENDING_REVIEW,
                review_priority=ReviewPriority.HIGHEST,
                ai_reason_text="树洞原文出现明确自伤意念，系统已拦截公开发布并推入最高优先级队列。",
                review_note=None,
                reviewed_by=None,
                reviewed_at=None,
                simulated_notice_log=None,
                created_at=self._at(days_ago=0, hour=11, minute=7),
                updated_at=self._at(days_ago=0, hour=11, minute=7),
            ),
        }
        self.session.add_all(alerts.values())
        self.session.flush()
        return alerts

    def _create_focus_entries(
        self,
        *,
        students: dict[str, StudentUser],
        submissions: dict[str, QuestionnaireSubmission],
        posts: dict[str, TreeholePost],
    ) -> list[FocusListEntry]:
        """Create focus-list rows for the watch and high risk demo students."""
        focus_entries = [
            FocusListEntry(
                student_id=students["watch"].id,
                source_type=CaseSourceType.ASSESSMENT,
                source_id=submissions["watch_sas"].id,
                reason_code="SAS_WATCH",
                reason_text="SAS 标准分处于需关注区间，需持续回访。",
                status=FocusListStatus.ACTIVE,
                created_at=self._at(days_ago=1, hour=20, minute=50),
            ),
            FocusListEntry(
                student_id=students["high"].id,
                source_type=CaseSourceType.TREEHOLE,
                source_id=posts["high_blocked"].id,
                reason_code="TREEHOLE_HIGH_RISK",
                reason_text="树洞高风险内容已拦截，等待人工复核与干预。",
                status=FocusListStatus.ACTIVE,
                created_at=self._at(days_ago=0, hour=11, minute=8),
            ),
        ]
        self.session.add_all(focus_entries)
        self.session.flush()
        return focus_entries

    def _create_intervention_logs(
        self,
        *,
        admin_user: AdminUser,
        alerts: dict[str, AlertCase],
    ) -> list[InterventionLog]:
        """Create a small but meaningful intervention timeline for A04."""
        watch_alert = alerts["watch_assessment"]
        intervention_logs = [
            InterventionLog(
                alert_case_id=watch_alert.id,
                admin_user_id=admin_user.id,
                action_type=InterventionActionType.ADD_NOTE,
                action_note="辅导员反馈学生愿意继续沟通，建议至少连续三天跟踪睡眠情况。",
                created_at=self._at(days_ago=0, hour=8, minute=30),
            ),
            InterventionLog(
                alert_case_id=watch_alert.id,
                admin_user_id=admin_user.id,
                action_type=InterventionActionType.SIMULATE_CONTACT,
                action_note="已模拟向辅导员值班手机发送提醒短信。",
                created_at=self._at(days_ago=1, hour=21, minute=10),
            ),
            InterventionLog(
                alert_case_id=watch_alert.id,
                admin_user_id=admin_user.id,
                action_type=InterventionActionType.CONFIRM_HIGH_RISK,
                action_note="人工复核后确认需要继续跟进，并转入干预处理中。",
                created_at=self._at(days_ago=1, hour=21, minute=0),
            ),
        ]
        self.session.add_all(intervention_logs)
        self.session.flush()
        return intervention_logs

    def _create_audit_logs(
        self,
        *,
        admin_user: AdminUser,
        alerts: dict[str, AlertCase],
        posts: dict[str, TreeholePost],
    ) -> list[AuditLog]:
        """Create seed audit examples so A07 has immediate display data."""
        audit_logs = [
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                actor_id=admin_user.id,
                action_code="ADMIN_HIDE_POST",
                target_type="treehole_post",
                target_id=posts["watch_hidden"].id,
                metadata_json={
                    "action": "hide",
                    "previous_status": "published",
                    "next_status": "hidden_by_admin",
                },
                ip_address=DEMO_AUDIT_IP_ADDRESS,
                created_at=self._at(days_ago=1, hour=20, minute=18),
            ),
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                actor_id=admin_user.id,
                action_code="ADMIN_CONFIRM_ALERT_CASE",
                target_type="alert_case",
                target_id=alerts["watch_assessment"].id,
                metadata_json={
                    "queue_status": AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION.value,
                },
                ip_address=DEMO_AUDIT_IP_ADDRESS,
                created_at=self._at(days_ago=1, hour=21, minute=0),
            ),
            AuditLog(
                actor_type=AuditActorType.SYSTEM,
                actor_id=None,
                action_code="SYSTEM_CREATE_SIMULATED_NOTICE_LOG",
                target_type="alert_case",
                target_id=alerts["watch_assessment"].id,
                metadata_json={
                    "queue_status": AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION.value,
                },
                ip_address=DEMO_AUDIT_IP_ADDRESS,
                created_at=self._at(days_ago=1, hour=21, minute=10),
            ),
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                actor_id=admin_user.id,
                action_code="ADMIN_ADD_INTERVENTION_NOTE",
                target_type="alert_case",
                target_id=alerts["watch_assessment"].id,
                metadata_json={
                    "queue_status": AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION.value,
                },
                ip_address=DEMO_AUDIT_IP_ADDRESS,
                created_at=self._at(days_ago=0, hour=8, minute=30),
            ),
        ]
        self.session.add_all(audit_logs)
        self.session.flush()
        return audit_logs

    def _at(self, *, days_ago: int, hour: int, minute: int) -> datetime:
        """Return one deterministic timestamp relative to the configured seed clock."""
        return self.now.replace(hour=hour, minute=minute, second=0, microsecond=0) - timedelta(
            days=days_ago
        )
