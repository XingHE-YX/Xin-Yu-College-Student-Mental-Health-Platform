"""Tests for questionnaire scoring services."""

from __future__ import annotations

from pathlib import Path

import pytest
from src.constants.questionnaire_enums import QuestionnaireRiskLevel
from src.services.questionnaire_scoring_service import (
    IncompleteQuestionnaireAnswersError,
    QuestionnaireScoringService,
)
from src.utils.validate_question_bank_seeds import load_seed_file

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTION_BANK_DIR = REPO_ROOT / "appendices" / "question_bank"
SEED_FILE_BY_CODE = {
    "SCREEN": "screen_questions.json",
    "SDS": "sds_questions.json",
    "SAS": "sas_questions.json",
    "SLEEP": "sleep_questions.json",
    "UPI": "upi_questions.json",
}


def load_seed(questionnaire_code: str):
    """Load one committed questionnaire seed file by questionnaire code."""
    return load_seed_file(QUESTION_BANK_DIR / SEED_FILE_BY_CODE[questionnaire_code])


def build_answers_for_target_total(
    questionnaire_code: str,
    *,
    target_total: int,
    min_score: int,
    max_score: int,
) -> dict[str, str]:
    """Build a complete answer mapping that yields the requested normalized total."""
    seed_file = load_seed(questionnaire_code)
    question_count = len(seed_file.questions)
    minimum_total = question_count * min_score
    maximum_total = question_count * max_score
    assert minimum_total <= target_total <= maximum_total

    desired_scores = [min_score] * question_count
    remaining = target_total - minimum_total
    for index in range(question_count):
        increment = min(max_score - min_score, remaining)
        desired_scores[index] += increment
        remaining -= increment

    assert remaining == 0

    answers: dict[str, str] = {}
    for question_seed, desired_score in zip(
        seed_file.questions, desired_scores, strict=True
    ):
        mapped_score = (
            5 - desired_score if question_seed.reverse_scored else desired_score
        )
        raw_value = next(
            option_value
            for option_value, score in question_seed.score_mapping.items()
            if score == mapped_score
        )
        answers[question_seed.question_id] = raw_value

    return answers


def build_upi_answers(
    *, upi_01: str, upi_02: str, upi_03: str, upi_04: str
) -> dict[str, str]:
    """Build a full UPI answer mapping."""
    return {
        "UPI_01": upi_01,
        "UPI_02": upi_02,
        "UPI_03": upi_03,
        "UPI_04": upi_04,
    }


def test_score_screen_threshold_boundary() -> None:
    """SCREEN should flip from low to watch at a raw score of 45."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SCREEN")

    low_result = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SCREEN", target_total=44, min_score=1, max_score=5
        ),
    )
    watch_result = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SCREEN", target_total=45, min_score=1, max_score=5
        ),
    )

    assert low_result.raw_score == 44
    assert low_result.standardized_score is None
    assert low_result.risk_level is QuestionnaireRiskLevel.LOW
    assert watch_result.raw_score == 45
    assert watch_result.standardized_score is None
    assert watch_result.risk_level is QuestionnaireRiskLevel.WATCH


def test_score_sleep_threshold_boundaries() -> None:
    """SLEEP should respect the 7/8/14/15 boundary contract."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SLEEP")

    result_7 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SLEEP", target_total=7, min_score=0, max_score=3
        ),
    )
    result_8 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SLEEP", target_total=8, min_score=0, max_score=3
        ),
    )
    result_14 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SLEEP", target_total=14, min_score=0, max_score=3
        ),
    )
    result_15 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SLEEP", target_total=15, min_score=0, max_score=3
        ),
    )

    assert result_7.risk_level is QuestionnaireRiskLevel.LOW
    assert result_8.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_14.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_15.risk_level is QuestionnaireRiskLevel.HIGH


def test_score_sds_threshold_boundaries() -> None:
    """SDS should respect standardized-score boundaries 53 and 63."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SDS")

    result_42 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SDS", target_total=42, min_score=1, max_score=4
        ),
    )
    result_43 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SDS", target_total=43, min_score=1, max_score=4
        ),
    )
    result_50 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SDS", target_total=50, min_score=1, max_score=4
        ),
    )
    result_51 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SDS", target_total=51, min_score=1, max_score=4
        ),
    )

    assert result_42.standardized_score == 52
    assert result_42.risk_level is QuestionnaireRiskLevel.LOW
    assert result_43.standardized_score == 53
    assert result_43.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_50.standardized_score == 62
    assert result_50.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_51.standardized_score == 63
    assert result_51.risk_level is QuestionnaireRiskLevel.HIGH


def test_score_sas_threshold_boundaries() -> None:
    """SAS should respect standardized-score boundaries 50 and 60."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SAS")

    result_39 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SAS", target_total=39, min_score=1, max_score=4
        ),
    )
    result_40 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SAS", target_total=40, min_score=1, max_score=4
        ),
    )
    result_47 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SAS", target_total=47, min_score=1, max_score=4
        ),
    )
    result_48 = service.score_seed_file(
        seed_file,
        build_answers_for_target_total(
            "SAS", target_total=48, min_score=1, max_score=4
        ),
    )

    assert result_39.standardized_score == 48
    assert result_39.risk_level is QuestionnaireRiskLevel.LOW
    assert result_40.standardized_score == 50
    assert result_40.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_47.standardized_score == 58
    assert result_47.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_48.standardized_score == 60
    assert result_48.risk_level is QuestionnaireRiskLevel.HIGH


def test_score_upi_keeps_auxiliary_results_low_without_hard_trigger_upgrade() -> None:
    """UPI scoring should stay auxiliary until hard-trigger logic is applied later."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("UPI")

    low_result = service.score_seed_file(
        seed_file,
        build_upi_answers(upi_01="no", upi_02="no", upi_03="no", upi_04="no"),
    )
    auxiliary_result = service.score_seed_file(
        seed_file,
        build_upi_answers(upi_01="yes", upi_02="yes", upi_03="no", upi_04="no"),
    )

    assert low_result.raw_score == 0
    assert low_result.risk_level is QuestionnaireRiskLevel.LOW
    assert auxiliary_result.raw_score == 2
    assert auxiliary_result.standardized_score is None
    assert auxiliary_result.risk_level is QuestionnaireRiskLevel.LOW


def test_score_zung_questionnaire_applies_reverse_scoring() -> None:
    """Reverse-scored Zung questions should invert the mapped score."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SDS")
    answers = {question.question_id: "1" for question in seed_file.questions}

    result = service.score_seed_file(seed_file, answers)
    scored_answer_by_code = {
        answer.question_code: answer for answer in result.scored_answers
    }

    assert scored_answer_by_code["SDS_01"].mapped_score == 1
    assert scored_answer_by_code["SDS_01"].normalized_score == 1
    assert scored_answer_by_code["SDS_02"].mapped_score == 1
    assert scored_answer_by_code["SDS_02"].normalized_score == 4


def test_score_questionnaire_requires_all_answers() -> None:
    """The scoring service should reject incomplete submissions."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SCREEN")
    answers = build_answers_for_target_total(
        "SCREEN",
        target_total=44,
        min_score=1,
        max_score=5,
    )
    answers.pop("SCREEN_15")

    with pytest.raises(IncompleteQuestionnaireAnswersError, match="SCREEN_15"):
        service.score_seed_file(seed_file, answers)
