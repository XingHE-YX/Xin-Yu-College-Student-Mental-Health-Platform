"""Scoring services for questionnaire submissions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.constants.questionnaire_enums import (
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionType,
)
from src.models.question_bank import QuestionBank
from src.schemas.question_bank_seed import QuestionBankSeedFile, QuestionSeed


class QuestionnaireScoringError(ValueError):
    """Base error for questionnaire scoring failures."""


class IncompleteQuestionnaireAnswersError(QuestionnaireScoringError):
    """Raised when submitted answers do not cover the full questionnaire."""


class InvalidQuestionnaireAnswerError(QuestionnaireScoringError):
    """Raised when a submitted answer is incompatible with question metadata."""


class QuestionnaireConfigurationError(QuestionnaireScoringError):
    """Raised when questionnaire metadata cannot support scoring."""


@dataclass(frozen=True, slots=True)
class ScoringQuestion:
    """Normalized question metadata needed by the scoring service."""

    question_code: str
    question_order: int
    question_type: QuestionType
    score_mapping: dict[str, int]
    reverse_scored: bool
    hard_trigger_rule: dict[str, Any] | None = None

    @classmethod
    def from_seed(
        cls,
        question_seed: QuestionSeed,
        *,
        question_order: int,
    ) -> ScoringQuestion:
        """Build a scoring question from a validated seed question."""
        return cls(
            question_code=question_seed.question_id,
            question_order=question_order,
            question_type=question_seed.question_type,
            score_mapping=question_seed.score_mapping,
            reverse_scored=question_seed.reverse_scored,
            hard_trigger_rule=(
                question_seed.hard_trigger_rule.model_dump()
                if question_seed.hard_trigger_rule is not None
                else None
            ),
        )

    @classmethod
    def from_question_bank(cls, question: QuestionBank) -> ScoringQuestion:
        """Build a scoring question from a persisted `question_bank` row."""
        return cls(
            question_code=question.question_code,
            question_order=question.question_order,
            question_type=question.question_type,
            score_mapping=question.score_mapping_json,
            reverse_scored=question.reverse_scored,
            hard_trigger_rule=question.hard_trigger_rule_json,
        )


@dataclass(frozen=True, slots=True)
class ScoredQuestionAnswer:
    """One normalized scored answer that can later be persisted."""

    question_code: str
    question_order: int
    selected_option: str
    raw_value: str
    mapped_score: int
    normalized_score: int
    reverse_scored: bool


@dataclass(frozen=True, slots=True)
class HardTriggerMatch:
    """A matched hard-trigger rule that upgrades questionnaire risk."""

    question_code: str
    question_order: int
    reason_code: str
    operator: str
    expected_value: int | str
    matched_value: int | str
    risk_level: QuestionnaireRiskLevel


@dataclass(frozen=True, slots=True)
class QuestionnaireScoreResult:
    """Structured result returned by questionnaire scorers."""

    questionnaire_code: str
    scoring_mode: QuestionnaireScoringMode
    question_count: int
    answered_count: int
    raw_score: int
    standardized_score: int | None
    risk_level: QuestionnaireRiskLevel
    hard_trigger_hit: bool
    hard_trigger_matches: list[HardTriggerMatch]
    scored_answers: list[ScoredQuestionAnswer]

    def to_snapshot(self) -> dict[str, Any]:
        """Return a JSON-friendly scoring snapshot for later persistence."""
        return {
            "questionnaire_code": self.questionnaire_code,
            "scoring_mode": self.scoring_mode.value,
            "question_count": self.question_count,
            "answered_count": self.answered_count,
            "raw_score": self.raw_score,
            "standardized_score": self.standardized_score,
            "risk_level": self.risk_level.value,
            "hard_trigger_hit": self.hard_trigger_hit,
            "hard_trigger_matches": [
                {
                    "question_code": match.question_code,
                    "question_order": match.question_order,
                    "reason_code": match.reason_code,
                    "operator": match.operator,
                    "expected_value": match.expected_value,
                    "matched_value": match.matched_value,
                    "risk_level": match.risk_level.value,
                }
                for match in self.hard_trigger_matches
            ],
            "answers": [
                {
                    "question_code": answer.question_code,
                    "question_order": answer.question_order,
                    "selected_option": answer.selected_option,
                    "raw_value": answer.raw_value,
                    "mapped_score": answer.mapped_score,
                    "normalized_score": answer.normalized_score,
                    "reverse_scored": answer.reverse_scored,
                }
                for answer in self.scored_answers
            ],
        }


class QuestionnaireScoringService:
    """Apply fixed scoring rules to validated questionnaire submissions."""

    def score_seed_file(
        self,
        seed_file: QuestionBankSeedFile,
        answers: Mapping[str, str],
    ) -> QuestionnaireScoreResult:
        """Score a questionnaire directly from a validated seed file."""
        questions = [
            ScoringQuestion.from_seed(question_seed, question_order=question_order)
            for question_order, question_seed in enumerate(seed_file.questions, start=1)
        ]
        return self.score_questionnaire(
            questionnaire_code=seed_file.template.code,
            scoring_mode=seed_file.template.scoring_mode,
            questions=questions,
            answers=answers,
        )

    def score_questionnaire(
        self,
        *,
        questionnaire_code: str,
        scoring_mode: QuestionnaireScoringMode,
        questions: list[ScoringQuestion],
        answers: Mapping[str, str],
    ) -> QuestionnaireScoreResult:
        """Score one questionnaire using normalized question metadata."""
        if not questions:
            raise QuestionnaireConfigurationError("questions cannot be empty")

        ordered_questions = sorted(
            questions, key=lambda question: question.question_order
        )
        question_codes = [question.question_code for question in ordered_questions]
        if len(question_codes) != len(set(question_codes)):
            raise QuestionnaireConfigurationError("question_code values must be unique")

        missing_answers = sorted(set(question_codes) - set(answers))
        if missing_answers:
            raise IncompleteQuestionnaireAnswersError(
                f"missing answers for: {', '.join(missing_answers)}"
            )

        unexpected_answers = sorted(set(answers) - set(question_codes))
        if unexpected_answers:
            raise InvalidQuestionnaireAnswerError(
                f"unexpected answers for: {', '.join(unexpected_answers)}"
            )

        scored_answers = [
            self._score_answer(
                question=question,
                scoring_mode=scoring_mode,
                raw_value=answers[question.question_code],
            )
            for question in ordered_questions
        ]
        raw_score = sum(answer.normalized_score for answer in scored_answers)
        standardized_score = (
            int(1.25 * raw_score)
            if scoring_mode is QuestionnaireScoringMode.ZUNG_STANDARD
            else None
        )
        hard_trigger_matches = [
            match
            for question, scored_answer in zip(
                ordered_questions, scored_answers, strict=True
            )
            if (match := self._evaluate_hard_trigger(question, scored_answer))
            is not None
        ]
        risk_level = self._determine_base_risk_level(
            questionnaire_code=questionnaire_code,
            raw_score=raw_score,
            standardized_score=standardized_score,
        )
        if hard_trigger_matches:
            risk_level = QuestionnaireRiskLevel.HIGH

        return QuestionnaireScoreResult(
            questionnaire_code=questionnaire_code,
            scoring_mode=scoring_mode,
            question_count=len(ordered_questions),
            answered_count=len(scored_answers),
            raw_score=raw_score,
            standardized_score=standardized_score,
            risk_level=risk_level,
            hard_trigger_hit=bool(hard_trigger_matches),
            hard_trigger_matches=hard_trigger_matches,
            scored_answers=scored_answers,
        )

    def score_screen(
        self,
        questions: list[ScoringQuestion],
        answers: Mapping[str, str],
    ) -> QuestionnaireScoreResult:
        """Score the 15-question quick screening questionnaire."""
        return self.score_questionnaire(
            questionnaire_code="SCREEN",
            scoring_mode=QuestionnaireScoringMode.SUM_1_5,
            questions=questions,
            answers=answers,
        )

    def score_sds(
        self,
        questions: list[ScoringQuestion],
        answers: Mapping[str, str],
    ) -> QuestionnaireScoreResult:
        """Score the SDS questionnaire with Zung standardization."""
        return self.score_questionnaire(
            questionnaire_code="SDS",
            scoring_mode=QuestionnaireScoringMode.ZUNG_STANDARD,
            questions=questions,
            answers=answers,
        )

    def score_sas(
        self,
        questions: list[ScoringQuestion],
        answers: Mapping[str, str],
    ) -> QuestionnaireScoreResult:
        """Score the SAS questionnaire with Zung standardization."""
        return self.score_questionnaire(
            questionnaire_code="SAS",
            scoring_mode=QuestionnaireScoringMode.ZUNG_STANDARD,
            questions=questions,
            answers=answers,
        )

    def score_sleep(
        self,
        questions: list[ScoringQuestion],
        answers: Mapping[str, str],
    ) -> QuestionnaireScoreResult:
        """Score the 15-question sleep questionnaire."""
        return self.score_questionnaire(
            questionnaire_code="SLEEP",
            scoring_mode=QuestionnaireScoringMode.SUM_0_3,
            questions=questions,
            answers=answers,
        )

    def score_upi(
        self,
        questions: list[ScoringQuestion],
        answers: Mapping[str, str],
    ) -> QuestionnaireScoreResult:
        """Score the optional UPI auxiliary questionnaire."""
        return self.score_questionnaire(
            questionnaire_code="UPI",
            scoring_mode=QuestionnaireScoringMode.YES_NO,
            questions=questions,
            answers=answers,
        )

    def _score_answer(
        self,
        *,
        question: ScoringQuestion,
        scoring_mode: QuestionnaireScoringMode,
        raw_value: str,
    ) -> ScoredQuestionAnswer:
        """Convert one submitted answer into a normalized scored answer."""
        if raw_value not in question.score_mapping:
            raise InvalidQuestionnaireAnswerError(
                f"unsupported answer '{raw_value}' for {question.question_code}"
            )

        mapped_score = question.score_mapping[raw_value]
        normalized_score = mapped_score
        if question.reverse_scored:
            if scoring_mode is not QuestionnaireScoringMode.ZUNG_STANDARD:
                raise QuestionnaireConfigurationError(
                    "reverse_scored questions are only supported for zung_standard questionnaires"
                )
            normalized_score = 5 - mapped_score

        return ScoredQuestionAnswer(
            question_code=question.question_code,
            question_order=question.question_order,
            selected_option=raw_value,
            raw_value=raw_value,
            mapped_score=mapped_score,
            normalized_score=normalized_score,
            reverse_scored=question.reverse_scored,
        )

    def _evaluate_hard_trigger(
        self,
        question: ScoringQuestion,
        scored_answer: ScoredQuestionAnswer,
    ) -> HardTriggerMatch | None:
        """Evaluate one question-level hard trigger against the submitted answer."""
        rule = question.hard_trigger_rule
        if rule is None:
            return None

        operator = rule.get("operator")
        expected_value = rule.get("value")
        reason_code = rule.get("reason_code")
        risk_level_value = rule.get("risk_level")

        if operator not in {">=", "=="}:
            raise QuestionnaireConfigurationError(
                f"unsupported hard trigger operator '{operator}' for {question.question_code}"
            )
        if not isinstance(reason_code, str) or not reason_code:
            raise QuestionnaireConfigurationError(
                f"hard trigger reason_code is missing for {question.question_code}"
            )
        if risk_level_value != QuestionnaireRiskLevel.HIGH.value:
            raise QuestionnaireConfigurationError(
                "unsupported hard trigger risk_level "
                f"'{risk_level_value}' for {question.question_code}"
            )

        if question.question_type is QuestionType.YES_NO:
            if operator != "==":
                raise QuestionnaireConfigurationError(
                    f"yes_no hard triggers must use '==' for {question.question_code}"
                )
            matched_value: int | str = scored_answer.raw_value
            is_match = matched_value == expected_value
        else:
            if operator == ">=":
                if not isinstance(expected_value, int):
                    raise QuestionnaireConfigurationError(
                        f"hard trigger '>=' expects an integer for {question.question_code}"
                    )
                matched_value = scored_answer.mapped_score
                is_match = matched_value >= expected_value
            elif isinstance(expected_value, int):
                matched_value = scored_answer.mapped_score
                is_match = matched_value == expected_value
            elif isinstance(expected_value, str):
                matched_value = scored_answer.raw_value
                is_match = matched_value == expected_value
            else:
                raise QuestionnaireConfigurationError(
                    f"unsupported hard trigger value for {question.question_code}"
                )

        if not is_match:
            return None

        return HardTriggerMatch(
            question_code=question.question_code,
            question_order=question.question_order,
            reason_code=reason_code,
            operator=operator,
            expected_value=expected_value,
            matched_value=matched_value,
            risk_level=QuestionnaireRiskLevel.HIGH,
        )

    def _determine_base_risk_level(
        self,
        *,
        questionnaire_code: str,
        raw_score: int,
        standardized_score: int | None,
    ) -> QuestionnaireRiskLevel:
        """Return the fixed risk level for one questionnaire result."""
        normalized_code = questionnaire_code.upper()
        if normalized_code == "SCREEN":
            return (
                QuestionnaireRiskLevel.WATCH
                if raw_score >= 45
                else QuestionnaireRiskLevel.LOW
            )

        if normalized_code == "SLEEP":
            if raw_score >= 15:
                return QuestionnaireRiskLevel.HIGH
            if raw_score >= 8:
                return QuestionnaireRiskLevel.WATCH
            return QuestionnaireRiskLevel.LOW

        if normalized_code == "SDS":
            if standardized_score is None:
                raise QuestionnaireConfigurationError(
                    "SDS requires a standardized score"
                )
            if standardized_score >= 63:
                return QuestionnaireRiskLevel.HIGH
            if standardized_score >= 53:
                return QuestionnaireRiskLevel.WATCH
            return QuestionnaireRiskLevel.LOW

        if normalized_code == "SAS":
            if standardized_score is None:
                raise QuestionnaireConfigurationError(
                    "SAS requires a standardized score"
                )
            if standardized_score >= 60:
                return QuestionnaireRiskLevel.HIGH
            if standardized_score >= 50:
                return QuestionnaireRiskLevel.WATCH
            return QuestionnaireRiskLevel.LOW

        if normalized_code == "UPI":
            return QuestionnaireRiskLevel.LOW

        raise QuestionnaireConfigurationError(
            f"unsupported questionnaire_code '{questionnaire_code}'"
        )
