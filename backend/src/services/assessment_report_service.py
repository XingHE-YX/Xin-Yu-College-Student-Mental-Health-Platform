"""Service layer for generating assessment report payloads."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.constants.questionnaire_enums import (
    AssessmentReportType,
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
)
from src.models.assessment_report import AssessmentReport
from src.models.questionnaire_submission import QuestionnaireSubmission
from src.schemas.question_bank_seed import QuestionBankSeedFile
from src.services.deepseek_service import DeepSeekJsonCompletionResult, DeepSeekService
from src.utils.validate_question_bank_seeds import discover_seed_files, load_seed_file

REPORT_VERSION = "v1.0"
QUESTIONNAIRE_DISPLAY_ORDER = ("SCREEN", "SDS", "SAS", "SLEEP", "UPI")
QUESTIONNAIRE_FLOW_STEP = {
    "SCREEN": "S05",
    "SDS": "S06",
    "SAS": "S07",
    "SLEEP": "S08",
    "UPI": "S09",
}
QUESTIONNAIRE_ACTION_LABEL = {
    "SCREEN": "开始快速筛查",
    "SDS": "继续完成 SDS",
    "SAS": "继续完成 SAS",
    "SLEEP": "继续完成睡眠问卷",
    "UPI": "查看 UPI 辅助筛查",
}
RISK_LABELS = {
    QuestionnaireRiskLevel.LOW: "低风险",
    QuestionnaireRiskLevel.WATCH: "需关注",
    QuestionnaireRiskLevel.HIGH: "高风险",
}
RISK_SURFACE_TONES = {
    QuestionnaireRiskLevel.LOW: "brand",
    QuestionnaireRiskLevel.WATCH: "warm",
    QuestionnaireRiskLevel.HIGH: "danger",
}
PRESENTATION_HINTS = {
    "hero_component": "hero-card",
    "badge_component": "result-badge",
    "progress_component": "progress-bar",
    "primary_button_component": "primary-button",
    "secondary_button_component": "secondary-button",
    "danger_button_component": "danger-button",
    "safety_banner_component": "safety-banner",
}
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SEED_DIRECTORY = REPO_ROOT / "appendices" / "question_bank"
DEFAULT_REPORT_MOCK_RESPONSE_PATH = REPO_ROOT / "backend" / "mock_report_response.json"


class AssessmentReportGenerationError(ValueError):
    """Base error for assessment report generation failures."""


class AssessmentReportConfigurationError(AssessmentReportGenerationError):
    """Raised when report generation cannot resolve questionnaire metadata."""


class AssessmentReportAIAnalysisError(AssessmentReportGenerationError):
    """Raised when an AI report-analysis payload cannot be normalized."""


class FullProfileLockedError(AssessmentReportGenerationError):
    """Raised when the required 70-question unlock chain is not complete."""

    def __init__(
        self,
        *,
        missing_questionnaire_codes: list[str],
        completed_required_questions: int,
        total_required_questions: int,
    ) -> None:
        self.missing_questionnaire_codes = missing_questionnaire_codes
        self.completed_required_questions = completed_required_questions
        self.total_required_questions = total_required_questions
        missing_text = ", ".join(missing_questionnaire_codes)
        super().__init__(
            "full profile report is locked until all required questionnaires are "
            f"completed; progress {completed_required_questions}/{total_required_questions}, "
            f"missing: {missing_text}"
        )


@dataclass(frozen=True, slots=True)
class QuestionnaireCatalogEntry:
    """Normalized questionnaire metadata used by report generation."""

    code: str
    name: str
    category: QuestionnaireCategory
    question_count: int
    unlock_required: bool
    is_active: bool

    @classmethod
    def from_seed_file(
        cls,
        seed_file: QuestionBankSeedFile,
    ) -> QuestionnaireCatalogEntry:
        """Build one catalog entry from a validated seed file."""
        return cls(
            code=seed_file.template.code,
            name=seed_file.template.name,
            category=seed_file.template.category,
            question_count=seed_file.template.question_count,
            unlock_required=seed_file.template.unlock_required,
            is_active=seed_file.template.is_active,
        )


@dataclass(frozen=True, slots=True)
class GeneratedAssessmentReport:
    """A report payload ready to persist in `assessment_reports`."""

    student_id: int
    report_type: AssessmentReportType
    report_version: str
    source_submission_ids: list[int]
    risk_level: QuestionnaireRiskLevel
    result_title: str
    content: dict[str, Any]

    def to_model(self) -> AssessmentReport:
        """Convert the generated payload into an ORM report instance."""
        return AssessmentReport(
            student_id=self.student_id,
            report_type=self.report_type,
            report_version=self.report_version,
            source_submission_ids_json=self.source_submission_ids,
            risk_level=self.risk_level,
            result_title=self.result_title,
            content_json=self.content,
        )


@dataclass(frozen=True, slots=True)
class ReportAIAnalysisSnapshot:
    """Normalized AI analysis block for one full-profile report."""

    analysis_summary: str
    model_assessed_risk_level: QuestionnaireRiskLevel
    dimensions: list[dict[str, str]]
    risk_factors: list[str]
    protective_factors: list[str]
    recommendations: list[dict[str, str]]
    manual_review_hint: str
    model_name: str
    fallback_used: bool
    fallback_reason: str | None
    request_payload_json: dict[str, Any]
    response_raw_json: dict[str, Any]

    def to_content_block(self) -> dict[str, Any]:
        """Return the frontend-facing AI analysis block."""
        return {
            "provider": "deepseek",
            "model_name": self.model_name,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "model_assessed_risk_level": self.model_assessed_risk_level.value,
            "analysis_summary": self.analysis_summary,
            "dimensions": self.dimensions,
            "risk_factors": self.risk_factors,
            "protective_factors": self.protective_factors,
            "recommendations": self.recommendations,
            "manual_review_hint": self.manual_review_hint,
        }


class AssessmentReportService:
    """Generate scale-result, summary, and full-profile report payloads."""

    def __init__(
        self,
        *,
        template_catalog: Sequence[QuestionnaireCatalogEntry] | None = None,
        seed_directory: Path = DEFAULT_SEED_DIRECTORY,
        deepseek_service: DeepSeekService | None = None,
    ) -> None:
        catalog_entries = list(template_catalog or self._load_catalog(seed_directory))
        if not catalog_entries:
            raise AssessmentReportConfigurationError(
                "questionnaire catalog cannot be empty"
            )

        catalog_by_code: dict[str, QuestionnaireCatalogEntry] = {}
        for entry in catalog_entries:
            normalized_code = entry.code.upper()
            if normalized_code in catalog_by_code:
                raise AssessmentReportConfigurationError(
                    f"duplicate questionnaire catalog entry '{normalized_code}'"
                )
            catalog_by_code[normalized_code] = entry

        self.catalog_by_code = catalog_by_code
        self.deepseek_service = deepseek_service

    def build_scale_result_report(
        self,
        submission: QuestionnaireSubmission,
        *,
        submissions: Sequence[QuestionnaireSubmission] | None = None,
    ) -> GeneratedAssessmentReport:
        """Generate one persisted scale-result report for a questionnaire."""
        catalog_entry = self._resolve_catalog_entry(submission)
        latest_submissions = self._select_latest_submissions(submissions or [submission])
        progress = self._build_unlock_progress(latest_submissions)
        next_actions = self._build_summary_actions(progress)
        if not next_actions:
            next_actions = [
                self._build_action(
                    label="查看完整报告",
                    flow_step="S10A",
                    button_variant="primary-button",
                    target_questionnaire_code=None,
                )
            ]

        content = {
            "schema_version": REPORT_VERSION,
            "page_type": "scale_result",
            "page_flow_step": QUESTIONNAIRE_FLOW_STEP.get(catalog_entry.code),
            "presentation": PRESENTATION_HINTS,
            "questionnaire": self._build_questionnaire_payload(catalog_entry),
            "hero_card": self._build_scale_hero(catalog_entry, submission),
            "result_badge": self._build_risk_badge(submission.risk_level),
            "score_summary": self._build_score_summary(catalog_entry.code, submission),
            "progress": progress,
            "summary_text": self._build_scale_summary_text(
                questionnaire_code=catalog_entry.code,
                risk_level=submission.risk_level,
            ),
            "support_actions": self._build_support_actions(
                risk_level=submission.risk_level,
                unlocked=progress["full_profile_unlocked"],
            ),
            "next_actions": next_actions,
            "disclaimer": self._build_disclaimer(catalog_entry.code),
        }
        if submission.hard_trigger_hit:
            content["hard_trigger_section"] = self._build_hard_trigger_section(submission)
        if submission.risk_level is QuestionnaireRiskLevel.HIGH:
            content["safety_banner"] = self._build_safety_banner()

        return GeneratedAssessmentReport(
            student_id=submission.student_id,
            report_type=AssessmentReportType.SCALE_RESULT,
            report_version=REPORT_VERSION,
            source_submission_ids=[submission.id],
            risk_level=submission.risk_level,
            result_title=f"{catalog_entry.name}结果",
            content=content,
        )

    def build_report_summary(
        self,
        submissions: Sequence[QuestionnaireSubmission],
    ) -> dict[str, Any]:
        """Build the summary state for the student report home page."""
        latest_submissions = self._select_latest_submissions(submissions)
        progress = self._build_unlock_progress(latest_submissions)
        state = self._determine_summary_state(
            has_any_results=bool(latest_submissions),
            unlocked=progress["full_profile_unlocked"],
        )
        overall_risk_level = self._aggregate_partial_risk_level(latest_submissions)
        payload = {
            "schema_version": REPORT_VERSION,
            "page_type": "report_summary",
            "page_flow_step": "S10",
            "presentation": PRESENTATION_HINTS,
            "state": state,
            "hero_card": self._build_summary_hero(state=state, progress=progress),
            "progress": progress,
            "scale_results": [
                self._build_scale_result_card(
                    self._resolve_catalog_entry(submission),
                    submission,
                )
                for submission in self._ordered_submissions(latest_submissions)
            ],
            "next_actions": self._build_summary_actions(progress),
            "disclaimer": self._build_disclaimer(None),
        }
        if overall_risk_level is not None:
            payload["overview_badge"] = self._build_risk_badge(overall_risk_level)
        if overall_risk_level is QuestionnaireRiskLevel.HIGH:
            payload["safety_banner"] = self._build_safety_banner()
        return payload

    def build_full_profile_report(
        self,
        submissions: Sequence[QuestionnaireSubmission],
    ) -> GeneratedAssessmentReport:
        """Generate the persisted full-profile report once 70 required answers exist."""
        latest_submissions = self._select_latest_submissions(submissions)
        progress = self._build_unlock_progress(latest_submissions)
        if not progress["full_profile_unlocked"]:
            raise FullProfileLockedError(
                missing_questionnaire_codes=[
                    item["code"] for item in progress["missing_required_questionnaires"]
                ],
                completed_required_questions=progress["required_questions_completed"],
                total_required_questions=progress["required_questions_total"],
            )

        student_id = self._resolve_student_id(latest_submissions.values())
        overall_risk_level = self._aggregate_full_profile_risk_level(latest_submissions)
        ordered_submissions = self._ordered_submissions(latest_submissions)
        ai_analysis = self._build_full_profile_ai_analysis(
            ordered_submissions=ordered_submissions,
            overall_risk_level=overall_risk_level,
        )
        content = {
            "schema_version": REPORT_VERSION,
            "page_type": "full_profile",
            "page_flow_step": "S10A",
            "presentation": PRESENTATION_HINTS,
            "hero_card": self._build_full_profile_hero(overall_risk_level),
            "result_badge": self._build_risk_badge(overall_risk_level),
            "unlock_status": progress,
            "integrated_summary": self._build_full_profile_summary(
                latest_submissions,
                overall_risk_level=overall_risk_level,
            ),
            "ai_integrated_analysis": ai_analysis.to_content_block(),
            "questionnaire_summaries": [
                self._build_scale_result_card(
                    self._resolve_catalog_entry(submission),
                    submission,
                )
                for submission in ordered_submissions
            ],
            "trend_placeholder": {
                "title": "趋势观察占位",
                "summary": (
                    "MVP 当前先展示最近一次完整测评结果，趋势图将在后续阶段接入历史数据后补齐。"
                ),
                "surface_tone": "brand",
            },
            "recommendations": self._build_support_actions(
                risk_level=overall_risk_level,
                unlocked=True,
            ),
            "disclaimer": self._build_disclaimer(None),
        }
        if overall_risk_level is QuestionnaireRiskLevel.HIGH:
            content["safety_banner"] = self._build_safety_banner()

        return GeneratedAssessmentReport(
            student_id=student_id,
            report_type=AssessmentReportType.FULL_PROFILE,
            report_version=REPORT_VERSION,
            source_submission_ids=[submission.id for submission in ordered_submissions],
            risk_level=overall_risk_level,
            result_title="完整综合画像报告",
            content=content,
        )

    def _load_catalog(self, seed_directory: Path) -> list[QuestionnaireCatalogEntry]:
        """Load questionnaire metadata from committed seed files."""
        seed_files = discover_seed_files(seed_directory)
        return [
            QuestionnaireCatalogEntry.from_seed_file(load_seed_file(path))
            for path in seed_files
        ]

    def _resolve_catalog_entry(
        self,
        submission: QuestionnaireSubmission,
    ) -> QuestionnaireCatalogEntry:
        """Resolve questionnaire metadata for one submission."""
        questionnaire_code = self._resolve_questionnaire_code(submission)
        catalog_entry = self.catalog_by_code.get(questionnaire_code)
        if catalog_entry is None:
            raise AssessmentReportConfigurationError(
                f"missing catalog entry for questionnaire '{questionnaire_code}'"
            )
        return catalog_entry

    def _resolve_questionnaire_code(self, submission: QuestionnaireSubmission) -> str:
        """Resolve a normalized questionnaire code from the submission snapshot."""
        snapshot = submission.scoring_snapshot_json or {}
        questionnaire_code = snapshot.get("questionnaire_code")
        if isinstance(questionnaire_code, str) and questionnaire_code:
            return questionnaire_code.upper()

        template = getattr(submission, "template", None)
        template_code = getattr(template, "code", None)
        if isinstance(template_code, str) and template_code:
            return template_code.upper()

        raise AssessmentReportConfigurationError(
            f"submission {submission.id} is missing questionnaire metadata"
        )

    def _select_latest_submissions(
        self,
        submissions: Sequence[QuestionnaireSubmission],
    ) -> dict[str, QuestionnaireSubmission]:
        """Keep only the latest submission per questionnaire code."""
        latest_submissions: dict[str, QuestionnaireSubmission] = {}
        for submission in submissions:
            questionnaire_code = self._resolve_questionnaire_code(submission)
            existing = latest_submissions.get(questionnaire_code)
            if existing is None or self._is_submission_newer(submission, existing):
                latest_submissions[questionnaire_code] = submission
        return latest_submissions

    def _is_submission_newer(
        self,
        candidate: QuestionnaireSubmission,
        current: QuestionnaireSubmission,
    ) -> bool:
        """Return whether the candidate submission should replace the current latest."""
        return self._submission_sort_key(candidate) > self._submission_sort_key(current)

    def _submission_sort_key(
        self,
        submission: QuestionnaireSubmission,
    ) -> tuple[datetime, datetime, int]:
        """Return a stable sort key for latest-submission comparisons."""
        created_at = getattr(submission, "created_at", None) or submission.submitted_at
        return (submission.submitted_at, created_at, submission.id or 0)

    def _ordered_submissions(
        self,
        latest_submissions: dict[str, QuestionnaireSubmission],
    ) -> list[QuestionnaireSubmission]:
        """Return submissions in canonical questionnaire order."""
        ordered_codes = [
            code
            for code in QUESTIONNAIRE_DISPLAY_ORDER
            if code in latest_submissions
        ]
        ordered_codes.extend(
            sorted(code for code in latest_submissions if code not in ordered_codes)
        )
        return [latest_submissions[code] for code in ordered_codes]

    def _build_unlock_progress(
        self,
        latest_submissions: dict[str, QuestionnaireSubmission],
    ) -> dict[str, Any]:
        """Build the summary payload for the fixed 70-question unlock chain."""
        required_entries = [
            self.catalog_by_code[code]
            for code in QUESTIONNAIRE_DISPLAY_ORDER
            if code in self.catalog_by_code and self.catalog_by_code[code].unlock_required
        ]
        required_total_questions = sum(entry.question_count for entry in required_entries)
        completed_required_entries = [
            entry for entry in required_entries if entry.code in latest_submissions
        ]
        missing_required_entries = [
            entry for entry in required_entries if entry.code not in latest_submissions
        ]
        completed_required_questions = sum(
            entry.question_count for entry in completed_required_entries
        )
        return {
            "component": "progress-bar",
            "required_questions_completed": completed_required_questions,
            "required_questions_total": required_total_questions,
            "required_questionnaires_completed": len(completed_required_entries),
            "required_questionnaires_total": len(required_entries),
            "full_profile_unlocked": not missing_required_entries
            and completed_required_questions == required_total_questions,
            "missing_required_questionnaires": [
                {
                    "code": entry.code,
                    "name": entry.name,
                    "question_count": entry.question_count,
                    "flow_step": QUESTIONNAIRE_FLOW_STEP.get(entry.code),
                }
                for entry in missing_required_entries
            ],
        }

    def _determine_summary_state(
        self,
        *,
        has_any_results: bool,
        unlocked: bool,
    ) -> str:
        """Map report progress into the summary page's three states."""
        if unlocked:
            return "unlocked"
        if has_any_results:
            return "partial"
        return "locked"

    def _aggregate_partial_risk_level(
        self,
        latest_submissions: dict[str, QuestionnaireSubmission],
    ) -> QuestionnaireRiskLevel | None:
        """Aggregate the report-home risk level from any available results."""
        if not latest_submissions:
            return None
        if any(
            submission.hard_trigger_hit
            or submission.risk_level is QuestionnaireRiskLevel.HIGH
            for submission in latest_submissions.values()
        ):
            return QuestionnaireRiskLevel.HIGH
        if any(
            submission.risk_level is QuestionnaireRiskLevel.WATCH
            for submission in latest_submissions.values()
        ):
            return QuestionnaireRiskLevel.WATCH
        return QuestionnaireRiskLevel.LOW

    def _aggregate_full_profile_risk_level(
        self,
        latest_submissions: dict[str, QuestionnaireSubmission],
    ) -> QuestionnaireRiskLevel:
        """Aggregate the final full-profile risk using the frozen PRD rules."""
        if any(
            submission.hard_trigger_hit for submission in latest_submissions.values()
        ):
            return QuestionnaireRiskLevel.HIGH

        sds = latest_submissions.get("SDS")
        sas = latest_submissions.get("SAS")
        sleep = latest_submissions.get("SLEEP")

        if sds is not None and sds.risk_level is QuestionnaireRiskLevel.HIGH:
            return QuestionnaireRiskLevel.HIGH
        if sas is not None and sas.risk_level is QuestionnaireRiskLevel.HIGH:
            return QuestionnaireRiskLevel.HIGH

        # The PRD's complete-data aggregation treats SDS/SAS positivity and sleep
        # concerns as "watch". SCREEN non-trigger watch remains a preliminary
        # signal and does not by itself elevate the final full-profile level.
        if sds is not None and sds.risk_level is QuestionnaireRiskLevel.WATCH:
            return QuestionnaireRiskLevel.WATCH
        if sas is not None and sas.risk_level is QuestionnaireRiskLevel.WATCH:
            return QuestionnaireRiskLevel.WATCH
        if sleep is not None and sleep.risk_level in {
            QuestionnaireRiskLevel.WATCH,
            QuestionnaireRiskLevel.HIGH,
        }:
            return QuestionnaireRiskLevel.WATCH

        return QuestionnaireRiskLevel.LOW

    def _resolve_student_id(
        self,
        submissions: Sequence[QuestionnaireSubmission],
    ) -> int:
        """Require all report source submissions to belong to one student."""
        student_ids = {submission.student_id for submission in submissions}
        if not student_ids:
            raise AssessmentReportConfigurationError("no submissions were provided")
        if len(student_ids) != 1:
            raise AssessmentReportConfigurationError(
                "all report submissions must belong to the same student"
            )
        return next(iter(student_ids))

    def _build_questionnaire_payload(
        self,
        entry: QuestionnaireCatalogEntry,
    ) -> dict[str, Any]:
        """Return stable questionnaire metadata for the frontend."""
        return {
            "code": entry.code,
            "name": entry.name,
            "category": entry.category.value,
            "question_count": entry.question_count,
            "unlock_required": entry.unlock_required,
            "flow_step": QUESTIONNAIRE_FLOW_STEP.get(entry.code),
        }

    def _build_risk_badge(
        self,
        risk_level: QuestionnaireRiskLevel,
    ) -> dict[str, str]:
        """Return badge metadata aligned to the shared frontend component."""
        return {
            "component": "result-badge",
            "risk_level": risk_level.value,
            "label": RISK_LABELS[risk_level],
            "surface_tone": RISK_SURFACE_TONES[risk_level],
        }

    def _build_scale_hero(
        self,
        entry: QuestionnaireCatalogEntry,
        submission: QuestionnaireSubmission,
    ) -> dict[str, str]:
        """Return the hero-card content for a single scale result page."""
        titles = {
            "SCREEN": {
                QuestionnaireRiskLevel.LOW: "当前状态整体平稳",
                QuestionnaireRiskLevel.WATCH: "近期压力值得继续留意",
                QuestionnaireRiskLevel.HIGH: "当前状态需要优先获得支持",
            },
            "SDS": {
                QuestionnaireRiskLevel.LOW: "情绪状态暂未出现明显抑郁信号",
                QuestionnaireRiskLevel.WATCH: "情绪压力已有持续累积迹象",
                QuestionnaireRiskLevel.HIGH: "情绪信号较强，建议尽快寻求支持",
            },
            "SAS": {
                QuestionnaireRiskLevel.LOW: "焦虑相关信号整体较轻",
                QuestionnaireRiskLevel.WATCH: "紧张与担忧已经影响到近期状态",
                QuestionnaireRiskLevel.HIGH: "紧张负荷较高，建议尽快寻求支持",
            },
            "SLEEP": {
                QuestionnaireRiskLevel.LOW: "睡眠与作息整体较稳定",
                QuestionnaireRiskLevel.WATCH: "睡眠与作息已出现波动",
                QuestionnaireRiskLevel.HIGH: "睡眠困扰较明显，需要尽快调整与支持",
            },
            "UPI": {
                QuestionnaireRiskLevel.LOW: "辅助筛查未出现明显高风险信号",
                QuestionnaireRiskLevel.WATCH: "辅助筛查存在需留意结果",
                QuestionnaireRiskLevel.HIGH: "辅助筛查命中了高风险信号",
            },
        }
        return {
            "eyebrow": "单量表结果",
            "title": titles[entry.code][submission.risk_level],
            "summary": self._build_scale_summary_text(
                questionnaire_code=entry.code,
                risk_level=submission.risk_level,
            ),
            "surface_tone": RISK_SURFACE_TONES[submission.risk_level],
        }

    def _build_summary_hero(
        self,
        *,
        state: str,
        progress: dict[str, Any],
    ) -> dict[str, str]:
        """Return the hero-card content for the report summary page."""
        if state == "unlocked":
            return {
                "eyebrow": "我的报告",
                "title": "完整报告已解锁",
                "summary": "你已完成 70 道必做题，可以查看综合画像、各量表摘要与调节建议。",
                "surface_tone": "brand",
            }
        if state == "partial":
            remaining = (
                progress["required_questions_total"]
                - progress["required_questions_completed"]
            )
            return {
                "eyebrow": "我的报告",
                "title": f"还差 {remaining} 题解锁完整报告",
                "summary": "已完成的量表结果可以先查看，完整综合画像会在必做问卷全部完成后开放。",
                "surface_tone": "warm",
            }
        return {
            "eyebrow": "我的报告",
            "title": "完成 70 道必做题后可查看完整报告",
            "summary": "建议先从快速筛查开始，系统会在每次提交后自动更新进度与单量表结果。",
            "surface_tone": "brand",
        }

    def _build_full_profile_hero(
        self,
        overall_risk_level: QuestionnaireRiskLevel,
    ) -> dict[str, str]:
        """Return the hero-card content for the unlocked full profile page."""
        titles = {
            QuestionnaireRiskLevel.LOW: "当前整体状态相对平稳",
            QuestionnaireRiskLevel.WATCH: "近期状态值得持续留意",
            QuestionnaireRiskLevel.HIGH: "当前状态需要优先获得支持",
        }
        summaries = {
            QuestionnaireRiskLevel.LOW: "四份必做问卷已完成，当前综合结果以稳定信号为主。",
            QuestionnaireRiskLevel.WATCH: (
                "四份必做问卷已完成，综合结果提示近期已有持续压力或作息影响。"
            ),
            QuestionnaireRiskLevel.HIGH: (
                "四份必做问卷已完成，综合结果出现了需要优先处理的高风险信号。"
            ),
        }
        return {
            "eyebrow": "完整综合画像报告",
            "title": titles[overall_risk_level],
            "summary": summaries[overall_risk_level],
            "surface_tone": RISK_SURFACE_TONES[overall_risk_level],
        }

    def _build_scale_summary_text(
        self,
        *,
        questionnaire_code: str,
        risk_level: QuestionnaireRiskLevel,
    ) -> str:
        """Return calm, non-diagnostic copy for one questionnaire result."""
        summary_copy = {
            "SCREEN": {
                QuestionnaireRiskLevel.LOW: (
                    "最近一周的情绪与压力信号整体平稳，可继续保持规律作息。"
                ),
                QuestionnaireRiskLevel.WATCH: (
                    "最近一周已出现较明显的压力或情绪波动，建议继续完成深度测评。"
                ),
                QuestionnaireRiskLevel.HIGH: (
                    "快速筛查已出现需要优先关注的高风险信号，"
                    "建议尽快联系可信赖的人或校内支持资源。"
                ),
            },
            "SDS": {
                QuestionnaireRiskLevel.LOW: "抑郁相关情绪信号整体较轻，当前未见明显高压迹象。",
                QuestionnaireRiskLevel.WATCH: (
                    "抑郁相关情绪已有一定累积，"
                    "建议结合后续量表与近期生活状态继续观察。"
                ),
                QuestionnaireRiskLevel.HIGH: (
                    "抑郁相关信号较强，建议尽快寻求线下支持，不要独自承受。"
                ),
            },
            "SAS": {
                QuestionnaireRiskLevel.LOW: "焦虑相关紧张感整体较轻，当前状态相对平稳。",
                QuestionnaireRiskLevel.WATCH: (
                    "近期紧张和担忧已有累积，建议主动调整作息并留意持续时间。"
                ),
                QuestionnaireRiskLevel.HIGH: (
                    "焦虑负荷较高，建议尽快联系可信赖的人、"
                    "辅导员或校内支持资源。"
                ),
            },
            "SLEEP": {
                QuestionnaireRiskLevel.LOW: "睡眠与作息整体稳定，可继续保持当前节律。",
                QuestionnaireRiskLevel.WATCH: "睡眠与作息已受到一定影响，建议优先处理休息与恢复。",
                QuestionnaireRiskLevel.HIGH: (
                    "睡眠困扰已经比较明显，建议尽快调整作息并主动寻求支持。"
                ),
            },
            "UPI": {
                QuestionnaireRiskLevel.LOW: "本次辅助筛查未出现明显高风险信号，仅作辅助参考。",
                QuestionnaireRiskLevel.WATCH: "本次辅助筛查存在需要继续留意的信号，仅作辅助参考。",
                QuestionnaireRiskLevel.HIGH: (
                    "本次辅助筛查命中了高风险信号，建议尽快联系线下支持资源。"
                ),
            },
        }
        return summary_copy[questionnaire_code][risk_level]

    def _build_score_summary(
        self,
        questionnaire_code: str,
        submission: QuestionnaireSubmission,
    ) -> list[dict[str, Any]]:
        """Return score cards used by scale result and report summary pages."""
        label = "总分"
        if questionnaire_code in {"SDS", "SAS"}:
            label = "粗分"
        if questionnaire_code == "UPI":
            label = "命中项数"

        score_items = [
            {
                "label": label,
                "value": submission.raw_score,
                "emphasis": "number",
            }
        ]
        if submission.standardized_score is not None:
            score_items.append(
                {
                    "label": "标准分",
                    "value": submission.standardized_score,
                    "emphasis": "number",
                }
            )
        return score_items

    def _build_scale_result_card(
        self,
        entry: QuestionnaireCatalogEntry,
        submission: QuestionnaireSubmission,
    ) -> dict[str, Any]:
        """Build one questionnaire result card for summary or full-profile pages."""
        payload = {
            "questionnaire": self._build_questionnaire_payload(entry),
            "submitted_at": submission.submitted_at.isoformat(timespec="seconds"),
            "result_badge": self._build_risk_badge(submission.risk_level),
            "score_summary": self._build_score_summary(entry.code, submission),
            "summary_text": self._build_scale_summary_text(
                questionnaire_code=entry.code,
                risk_level=submission.risk_level,
            ),
        }
        if submission.hard_trigger_hit:
            payload["hard_trigger_hit"] = True
        return payload

    def _build_support_actions(
        self,
        *,
        risk_level: QuestionnaireRiskLevel,
        unlocked: bool,
    ) -> list[dict[str, str]]:
        """Return calm follow-up suggestions for result and report pages."""
        if risk_level is QuestionnaireRiskLevel.LOW:
            suggestions = [
                "保持基本作息稳定，优先保证睡眠、饮食和规律活动。",
                "如果近期压力重新上升，可以再次完成测评或查看帮助资源。",
            ]
            if not unlocked:
                suggestions.append("继续完成剩余必做问卷，获取更完整的综合画像。")
            return [{"title": "接下来可以这样做", "summary": item} for item in suggestions]

        if risk_level is QuestionnaireRiskLevel.WATCH:
            suggestions = [
                "给自己留出稳定休息时间，优先处理睡眠和日常节律。",
                "把近期压力变化告诉可信赖的人，必要时联系辅导员或校内心理中心。",
            ]
            if not unlocked:
                suggestions.append("继续完成剩余必做问卷，避免只凭部分结果下判断。")
            return [{"title": "建议优先处理", "summary": item} for item in suggestions]

        return [
            {
                "title": "请先不要独自承受",
                "summary": "尽快联系可信赖的人、辅导员或校内心理中心，优先获得线下支持。",
            },
            {
                "title": "先降低独处风险",
                "summary": "如果你此刻情绪很重，尽量让自己处在有人可联系、可照应的环境中。",
            },
            {
                "title": "需要时立即求助",
                "summary": "若出现强烈自伤冲动或无法保证自身安全，请立刻寻求线下紧急帮助。",
            },
        ]

    def _build_summary_actions(
        self,
        progress: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build CTA metadata for the report summary page."""
        if progress["full_profile_unlocked"]:
            return [
                self._build_action(
                    label="查看完整报告",
                    flow_step="S10A",
                    button_variant="primary-button",
                    target_questionnaire_code=None,
                ),
                self._build_action(
                    label="查看帮助资源",
                    flow_step="S15",
                    button_variant="secondary-button",
                    target_questionnaire_code=None,
                ),
            ]

        if progress["missing_required_questionnaires"]:
            first_missing = progress["missing_required_questionnaires"][0]
            actions = [
                self._build_action(
                    label=QUESTIONNAIRE_ACTION_LABEL[first_missing["code"]],
                    flow_step=first_missing["flow_step"],
                    button_variant="primary-button",
                    target_questionnaire_code=first_missing["code"],
                )
            ]
            if len(progress["missing_required_questionnaires"]) > 1:
                second_missing = progress["missing_required_questionnaires"][1]
                actions.append(
                    self._build_action(
                        label=QUESTIONNAIRE_ACTION_LABEL[second_missing["code"]],
                        flow_step=second_missing["flow_step"],
                        button_variant="secondary-button",
                        target_questionnaire_code=second_missing["code"],
                    )
                )
            return actions

        return []

    def _build_action(
        self,
        *,
        label: str,
        flow_step: str | None,
        button_variant: str,
        target_questionnaire_code: str | None,
    ) -> dict[str, Any]:
        """Build one frontend CTA descriptor."""
        return {
            "label": label,
            "flow_step": flow_step,
            "button_variant": button_variant,
            "target_questionnaire_code": target_questionnaire_code,
        }

    def _build_hard_trigger_section(
        self,
        submission: QuestionnaireSubmission,
    ) -> dict[str, Any]:
        """Format hard-trigger detail from the scoring snapshot."""
        snapshot = submission.scoring_snapshot_json or {}
        matches = snapshot.get("hard_trigger_matches", [])
        formatted_matches = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            formatted_matches.append(
                {
                    "question_code": match.get("question_code"),
                    "reason_code": match.get("reason_code"),
                    "operator": match.get("operator"),
                    "expected_value": match.get("expected_value"),
                    "matched_value": match.get("matched_value"),
                }
            )
        return {
            "component": "safety-banner",
            "title": "本次作答命中了高风险触发规则",
            "summary": "系统已将该结果提升为高风险，请优先查看求助建议并尽快联系线下支持。",
            "matches": formatted_matches,
        }

    def _build_safety_banner(self) -> dict[str, Any]:
        """Return the shared safety-banner payload for high-risk states."""
        return {
            "component": "safety-banner",
            "title": "当前结果提示你需要优先获得支持",
            "summary": (
                "这不是诊断结论，但已经出现较强风险信号。"
                "建议尽快联系可信赖的人、辅导员或校内心理中心。"
            ),
            "primary_action": self._build_action(
                label="查看帮助资源",
                flow_step="S15",
                button_variant="danger-button",
                target_questionnaire_code=None,
            ),
        }

    def _build_disclaimer(self, questionnaire_code: str | None) -> str:
        """Return the shared non-diagnostic disclaimer text."""
        if questionnaire_code == "UPI":
            return "UPI 结果仅作辅助参考，不参与完整报告总分，也不构成诊断。"
        return "本结果用于自助筛查与校园支持参考，不构成诊断。"

    def _build_full_profile_ai_analysis(
        self,
        *,
        ordered_submissions: list[QuestionnaireSubmission],
        overall_risk_level: QuestionnaireRiskLevel,
    ) -> ReportAIAnalysisSnapshot:
        """Build an AI-assisted multidimensional analysis block for the full report."""
        if self.deepseek_service is None:
            return self._build_rule_based_ai_analysis_snapshot(
                ordered_submissions=ordered_submissions,
                overall_risk_level=overall_risk_level,
                fallback_reason="DeepSeek service is not configured for report analysis",
            )

        try:
            completion_result = self.deepseek_service.create_json_completion_with_fallback(
                system_prompt=(
                    "You are an extremely professional clinical-psychology expert and "
                    "campus mental-health report consultant. Analyze scored questionnaire "
                    "results from multiple dimensions and return a student-facing, "
                    "non-diagnostic JSON report. Your style is warm, tactful, comforting, "
                    "and academically careful: avoid blunt conclusions, avoid medical "
                    "diagnoses, explain risk gently, and provide practical support "
                    "suggestions that a college student can actually follow."
                ),
                user_prompt=self._build_full_profile_ai_prompt(
                    ordered_submissions=ordered_submissions,
                    overall_risk_level=overall_risk_level,
                ),
                response_example={
                    "analysis_summary": "brief integrated summary",
                    "model_assessed_risk_level": "low",
                    "dimensions": [
                        {
                            "name": "情绪状态",
                            "level": "low",
                            "evidence": "brief evidence from SDS",
                        }
                    ],
                    "risk_factors": ["one possible risk factor"],
                    "protective_factors": ["one protective factor"],
                    "recommendations": [
                        {
                            "title": "one action title",
                            "summary": "brief action summary",
                        }
                    ],
                    "manual_review_hint": "brief review hint",
                },
                max_tokens=1200,
                mock_response_path=DEFAULT_REPORT_MOCK_RESPONSE_PATH,
            )
            return self._normalize_report_ai_completion_result(
                completion_result,
                fallback_risk_level=overall_risk_level,
            )
        except AssessmentReportAIAnalysisError as exc:
            return self._build_rule_based_ai_analysis_snapshot(
                ordered_submissions=ordered_submissions,
                overall_risk_level=overall_risk_level,
                fallback_reason=str(exc),
            )

    def _build_full_profile_ai_prompt(
        self,
        *,
        ordered_submissions: list[QuestionnaireSubmission],
        overall_risk_level: QuestionnaireRiskLevel,
    ) -> str:
        """Build the structured prompt sent to DeepSeek for report interpretation."""
        submission_payload = [
            self._build_ai_submission_payload(submission)
            for submission in ordered_submissions
        ]
        return (
            "Analyze this student's completed questionnaire profile. Use the fixed "
            "risk levels as source evidence, but add multidimensional interpretation "
            "across emotion, anxiety, sleep, pressure, protective factors, and review "
            "priority. Return JSON only.\n"
            f"Overall rule risk level: {overall_risk_level.value}\n"
            f"Questionnaire results: {submission_payload}"
        )

    def _build_ai_submission_payload(
        self,
        submission: QuestionnaireSubmission,
    ) -> dict[str, Any]:
        """Return compact questionnaire evidence for AI report analysis."""
        catalog_entry = self._resolve_catalog_entry(submission)
        return {
            "code": catalog_entry.code,
            "name": catalog_entry.name,
            "raw_score": submission.raw_score,
            "standardized_score": submission.standardized_score,
            "risk_level": submission.risk_level.value,
            "hard_trigger_hit": submission.hard_trigger_hit,
            "submitted_at": submission.submitted_at.isoformat(timespec="seconds"),
            "summary_text": self._build_scale_summary_text(
                questionnaire_code=catalog_entry.code,
                risk_level=submission.risk_level,
            ),
            "hard_trigger_matches": (
                submission.scoring_snapshot_json or {}
            ).get("hard_trigger_matches", []),
        }

    def _normalize_report_ai_completion_result(
        self,
        completion_result: DeepSeekJsonCompletionResult,
        *,
        fallback_risk_level: QuestionnaireRiskLevel,
    ) -> ReportAIAnalysisSnapshot:
        """Normalize one DeepSeek or mock completion into a report content block."""
        content_json = completion_result.content_json
        analysis_summary = self._require_text_field(
            content_json,
            field_name="analysis_summary",
        )
        risk_level_raw = content_json.get("model_assessed_risk_level")
        try:
            model_assessed_risk_level = QuestionnaireRiskLevel(str(risk_level_raw))
        except ValueError:
            model_assessed_risk_level = fallback_risk_level

        dimensions = self._normalize_ai_dimensions(content_json.get("dimensions", []))
        risk_factors = self._normalize_string_list(
            content_json.get("risk_factors", []),
            field_name="risk_factors",
        )
        protective_factors = self._normalize_string_list(
            content_json.get("protective_factors", []),
            field_name="protective_factors",
        )
        recommendations = self._normalize_ai_recommendations(
            content_json.get("recommendations", [])
        )
        manual_review_hint = self._require_text_field(
            content_json,
            field_name="manual_review_hint",
        )

        return ReportAIAnalysisSnapshot(
            analysis_summary=analysis_summary,
            model_assessed_risk_level=model_assessed_risk_level,
            dimensions=dimensions,
            risk_factors=risk_factors,
            protective_factors=protective_factors,
            recommendations=recommendations,
            manual_review_hint=manual_review_hint,
            model_name=completion_result.effective_model_name,
            fallback_used=completion_result.fallback_used,
            fallback_reason=completion_result.fallback_reason,
            request_payload_json=completion_result.request_payload,
            response_raw_json=completion_result.response_payload,
        )

    def _build_rule_based_ai_analysis_snapshot(
        self,
        *,
        ordered_submissions: list[QuestionnaireSubmission],
        overall_risk_level: QuestionnaireRiskLevel,
        fallback_reason: str,
    ) -> ReportAIAnalysisSnapshot:
        """Return a deterministic report-analysis block when AI output is unavailable."""
        dimensions = [
            self._build_rule_based_dimension(submission)
            for submission in ordered_submissions
        ]
        return ReportAIAnalysisSnapshot(
            analysis_summary=self._build_full_profile_summary(
                self._select_latest_submissions(ordered_submissions),
                overall_risk_level=overall_risk_level,
            ),
            model_assessed_risk_level=overall_risk_level,
            dimensions=dimensions,
            risk_factors=self._build_rule_based_risk_factors(
                ordered_submissions=ordered_submissions,
                overall_risk_level=overall_risk_level,
            ),
            protective_factors=self._build_rule_based_protective_factors(
                overall_risk_level=overall_risk_level
            ),
            recommendations=self._build_support_actions(
                risk_level=overall_risk_level,
                unlocked=True,
            ),
            manual_review_hint=self._build_rule_based_manual_review_hint(
                overall_risk_level
            ),
            model_name="rule_based_fallback",
            fallback_used=True,
            fallback_reason=fallback_reason,
            request_payload_json={
                "mode": "rule_based_report_analysis",
                "source_submission_ids": [
                    submission.id for submission in ordered_submissions
                ],
            },
            response_raw_json={
                "source": "rule_based_fallback",
                "risk_level": overall_risk_level.value,
            },
        )

    def _build_rule_based_dimension(
        self,
        submission: QuestionnaireSubmission,
    ) -> dict[str, str]:
        """Build one fallback dimension from questionnaire metadata."""
        catalog_entry = self._resolve_catalog_entry(submission)
        return {
            "name": catalog_entry.name,
            "level": submission.risk_level.value,
            "evidence": self._build_scale_summary_text(
                questionnaire_code=catalog_entry.code,
                risk_level=submission.risk_level,
            ),
        }

    def _build_rule_based_risk_factors(
        self,
        *,
        ordered_submissions: list[QuestionnaireSubmission],
        overall_risk_level: QuestionnaireRiskLevel,
    ) -> list[str]:
        """Build concise fallback risk factors from latest questionnaire results."""
        if overall_risk_level is QuestionnaireRiskLevel.LOW:
            return ["当前量表结果未出现需要立即升级处理的风险信号。"]

        factors: list[str] = []
        for submission in ordered_submissions:
            if submission.risk_level is QuestionnaireRiskLevel.LOW:
                continue
            catalog_entry = self._resolve_catalog_entry(submission)
            factors.append(f"{catalog_entry.name}结果为{RISK_LABELS[submission.risk_level]}。")
        return factors or ["综合结果提示近期状态值得继续留意。"]

    def _build_rule_based_protective_factors(
        self,
        *,
        overall_risk_level: QuestionnaireRiskLevel,
    ) -> list[str]:
        """Build fallback protective factors for the AI block."""
        factors = ["学生已完成完整测评链路，系统具备较完整的自助筛查信息。"]
        if overall_risk_level is not QuestionnaireRiskLevel.HIGH:
            factors.append("当前未出现需要立即拦截的高风险综合结论。")
        return factors

    def _build_rule_based_manual_review_hint(
        self,
        overall_risk_level: QuestionnaireRiskLevel,
    ) -> str:
        """Return a fallback review hint aligned with the aggregate risk."""
        if overall_risk_level is QuestionnaireRiskLevel.HIGH:
            return "建议后台优先复核，并提醒学生尽快联系线下支持资源。"
        if overall_risk_level is QuestionnaireRiskLevel.WATCH:
            return "建议继续观察，必要时进入重点关注列表。"
        return "当前无需直接升级人工复核，但应保留主动求助入口。"

    def _require_text_field(
        self,
        content_json: dict[str, Any],
        *,
        field_name: str,
    ) -> str:
        """Return a required non-blank string from an AI payload."""
        value = content_json.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise AssessmentReportAIAnalysisError(
                f"report AI analysis payload contains an invalid {field_name}"
            )
        return value.strip()

    def _normalize_ai_dimensions(self, value: object) -> list[dict[str, str]]:
        """Normalize AI dimension entries for report rendering."""
        if not isinstance(value, list):
            raise AssessmentReportAIAnalysisError(
                "report AI analysis payload contains invalid dimensions"
            )

        dimensions: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                raise AssessmentReportAIAnalysisError(
                    "report AI analysis payload contains invalid dimensions"
                )
            name = item.get("name")
            level = item.get("level")
            evidence = item.get("evidence")
            if (
                not isinstance(name, str)
                or not name.strip()
                or str(level) not in {level.value for level in QuestionnaireRiskLevel}
                or not isinstance(evidence, str)
                or not evidence.strip()
            ):
                raise AssessmentReportAIAnalysisError(
                    "report AI analysis payload contains invalid dimensions"
                )
            dimensions.append(
                {
                    "name": name.strip(),
                    "level": str(level),
                    "evidence": evidence.strip(),
                }
            )
        return dimensions

    def _normalize_ai_recommendations(self, value: object) -> list[dict[str, str]]:
        """Normalize AI recommendations for report rendering."""
        if not isinstance(value, list):
            raise AssessmentReportAIAnalysisError(
                "report AI analysis payload contains invalid recommendations"
            )

        recommendations: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                raise AssessmentReportAIAnalysisError(
                    "report AI analysis payload contains invalid recommendations"
                )
            title = item.get("title")
            summary = item.get("summary")
            if (
                not isinstance(title, str)
                or not title.strip()
                or not isinstance(summary, str)
                or not summary.strip()
            ):
                raise AssessmentReportAIAnalysisError(
                    "report AI analysis payload contains invalid recommendations"
                )
            recommendations.append(
                {
                    "title": title.strip(),
                    "summary": summary.strip(),
                }
            )
        return recommendations

    def _normalize_string_list(
        self,
        value: object,
        *,
        field_name: str,
    ) -> list[str]:
        """Validate that one AI payload field is a string array and trim empty items."""
        if not isinstance(value, list):
            raise AssessmentReportAIAnalysisError(
                f"report AI analysis payload contains an invalid {field_name}"
            )

        normalized_items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise AssessmentReportAIAnalysisError(
                    f"report AI analysis payload contains an invalid {field_name}"
                )
            normalized_item = item.strip()
            if normalized_item:
                normalized_items.append(normalized_item)
        return normalized_items

    def _build_full_profile_summary(
        self,
        latest_submissions: dict[str, QuestionnaireSubmission],
        *,
        overall_risk_level: QuestionnaireRiskLevel,
    ) -> str:
        """Build the integrated narrative summary for the unlocked full profile."""
        if overall_risk_level is QuestionnaireRiskLevel.HIGH:
            return (
                "综合结果显示当前已出现需要优先处理的高风险信号。请不要只依赖线上结果，"
                "尽快联系可信赖的人、辅导员或校内心理中心，优先获得线下支持。"
            )

        sds = latest_submissions.get("SDS")
        sas = latest_submissions.get("SAS")
        sleep = latest_submissions.get("SLEEP")

        if overall_risk_level is QuestionnaireRiskLevel.WATCH:
            focus_areas: list[str] = []
            if sds is not None and sds.risk_level is QuestionnaireRiskLevel.WATCH:
                focus_areas.append("情绪低落感已有持续累积")
            if sas is not None and sas.risk_level is QuestionnaireRiskLevel.WATCH:
                focus_areas.append("紧张与担忧已经影响近期状态")
            if sleep is not None and sleep.risk_level in {
                QuestionnaireRiskLevel.WATCH,
                QuestionnaireRiskLevel.HIGH,
            }:
                focus_areas.append("睡眠与作息需要优先调整")
            joined_focus_areas = "；".join(focus_areas) or "近期状态值得持续留意"
            return (
                f"综合结果提示：{joined_focus_areas}。建议先稳定作息，"
                "并把最近的压力变化告诉可信赖的人。"
            )

        return (
            "综合结果以稳定信号为主，当前未见需要立即升级处理的量表风险。"
            "如果后续状态出现明显变化，建议再次完成测评并按需查看帮助资源。"
        )
