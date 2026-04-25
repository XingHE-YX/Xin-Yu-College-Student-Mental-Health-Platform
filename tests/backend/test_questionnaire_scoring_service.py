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


def matches_hard_trigger(question_seed, raw_value: str) -> bool:
    """Return whether one raw answer value would hit the question's hard trigger."""
    rule = question_seed.hard_trigger_rule
    if rule is None:
        return False

    if question_seed.question_type.value == "yes_no":
        return rule.operator == "==" and raw_value == rule.value

    mapped_score = question_seed.score_mapping[raw_value]
    if rule.operator == ">=":
        return mapped_score >= rule.value
    if isinstance(rule.value, int):
        return mapped_score == rule.value
    return raw_value == rule.value


def build_non_trigger_score_options(question_seed) -> dict[int, str]:
    """Return normalized-score -> raw-value choices that avoid hard triggers."""
    score_options: dict[int, str] = {}
    for raw_value, mapped_score in question_seed.score_mapping.items():
        if matches_hard_trigger(question_seed, raw_value):
            continue
        normalized_score = (
            5 - mapped_score if question_seed.reverse_scored else mapped_score
        )
        score_options[normalized_score] = raw_value

    if not score_options:
        raise AssertionError(
            f"no non-trigger score options for {question_seed.question_id}"
        )
    return score_options


def build_answers_for_target_total(
    questionnaire_code: str,
    *,
    target_total: int,
    min_score: int,
    max_score: int,
) -> dict[str, str]:
    """Build a complete answer mapping that yields the requested normalized total."""
    seed_file = load_seed(questionnaire_code)
    score_options_by_question = [
        build_non_trigger_score_options(question_seed)
        for question_seed in seed_file.questions
    ]
    minimum_total = sum(
        min(score_options) for score_options in score_options_by_question
    )
    maximum_total = sum(
        max(score_options) for score_options in score_options_by_question
    )
    assert minimum_total <= target_total <= maximum_total

    desired_scores = [min(score_options) for score_options in score_options_by_question]
    remaining = target_total - minimum_total
    for index, score_options in enumerate(score_options_by_question):
        max_increment = max(score_options) - desired_scores[index]
        increment = min(max_increment, remaining)
        desired_scores[index] += increment
        remaining -= increment

    assert remaining == 0

    answers: dict[str, str] = {}
    for question_seed, desired_score in zip(
        seed_file.questions, desired_scores, strict=True
    ):
        raw_value = build_non_trigger_score_options(question_seed)[desired_score]
        answers[question_seed.question_id] = raw_value

    return answers


def build_low_risk_answers(questionnaire_code: str) -> dict[str, str]:
    """Build a complete answer set that minimizes normalized questionnaire risk."""
    seed_file = load_seed(questionnaire_code)
    answers: dict[str, str] = {}
    for question_seed in seed_file.questions:
        if question_seed.question_type.value == "yes_no":
            answers[question_seed.question_id] = "no"
            continue

        score_options = build_non_trigger_score_options(question_seed)
        desired_score = min(score_options)
        raw_value = score_options[desired_score]
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
    assert low_result.hard_trigger_hit is False
    assert watch_result.raw_score == 45
    assert watch_result.standardized_score is None
    assert watch_result.risk_level is QuestionnaireRiskLevel.WATCH
    assert watch_result.hard_trigger_hit is False


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
    assert result_7.hard_trigger_hit is False
    assert result_8.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_8.hard_trigger_hit is False
    assert result_14.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_14.hard_trigger_hit is False
    assert result_15.risk_level is QuestionnaireRiskLevel.HIGH
    assert result_15.hard_trigger_hit is False


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
    assert result_42.hard_trigger_hit is False
    assert result_43.standardized_score == 53
    assert result_43.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_43.hard_trigger_hit is False
    assert result_50.standardized_score == 62
    assert result_50.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_50.hard_trigger_hit is False
    assert result_51.standardized_score == 63
    assert result_51.risk_level is QuestionnaireRiskLevel.HIGH
    assert result_51.hard_trigger_hit is False


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
    assert result_39.hard_trigger_hit is False
    assert result_40.standardized_score == 50
    assert result_40.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_40.hard_trigger_hit is False
    assert result_47.standardized_score == 58
    assert result_47.risk_level is QuestionnaireRiskLevel.WATCH
    assert result_47.hard_trigger_hit is False
    assert result_48.standardized_score == 60
    assert result_48.risk_level is QuestionnaireRiskLevel.HIGH
    assert result_48.hard_trigger_hit is False


def test_score_upi_no_trigger_stays_low() -> None:
    """UPI without hard triggers should remain a low-risk auxiliary result."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("UPI")

    low_result = service.score_seed_file(
        seed_file,
        build_upi_answers(upi_01="no", upi_02="no", upi_03="no", upi_04="no"),
    )

    assert low_result.raw_score == 0
    assert low_result.risk_level is QuestionnaireRiskLevel.LOW
    assert low_result.hard_trigger_hit is False
    assert low_result.hard_trigger_matches == []


def test_screen_hard_trigger_upgrades_result_to_high() -> None:
    """SCREEN_15 >= 4 should upgrade the result to high risk."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SCREEN")
    answers = build_low_risk_answers("SCREEN")
    answers["SCREEN_15"] = "4"

    result = service.score_seed_file(seed_file, answers)

    assert result.raw_score == 18
    assert result.risk_level is QuestionnaireRiskLevel.HIGH
    assert result.hard_trigger_hit is True
    assert len(result.hard_trigger_matches) == 1
    assert result.hard_trigger_matches[0].question_code == "SCREEN_15"
    assert result.hard_trigger_matches[0].reason_code == "HT-01"
    assert result.to_snapshot()["hard_trigger_hit"] is True


def test_sds_hard_trigger_upgrades_result_to_high() -> None:
    """SDS_15 >= 4 should upgrade a low base score to high risk."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SDS")
    answers = build_low_risk_answers("SDS")
    answers["SDS_15"] = "4"

    result = service.score_seed_file(seed_file, answers)

    assert result.standardized_score == 28
    assert result.risk_level is QuestionnaireRiskLevel.HIGH
    assert result.hard_trigger_hit is True
    assert result.hard_trigger_matches[0].question_code == "SDS_15"
    assert result.hard_trigger_matches[0].matched_value == 4
    assert result.hard_trigger_matches[0].reason_code == "HT-02"


def test_sas_hard_trigger_upgrades_result_to_high_even_on_reverse_scored_question() -> (
    None
):
    """SAS_13 >= 4 should trigger before reverse scoring lowers the normalized score."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("SAS")
    answers = build_low_risk_answers("SAS")
    answers["SAS_13"] = "4"

    result = service.score_seed_file(seed_file, answers)

    assert result.standardized_score == 25
    assert result.risk_level is QuestionnaireRiskLevel.HIGH
    assert result.hard_trigger_hit is True
    assert result.hard_trigger_matches[0].question_code == "SAS_13"
    assert result.hard_trigger_matches[0].matched_value == 4
    assert result.hard_trigger_matches[0].reason_code == "HT-03"


def test_upi_hard_trigger_on_upi_01_upgrades_result_to_high() -> None:
    """UPI_01 = yes should upgrade the auxiliary questionnaire to high risk."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("UPI")

    result = service.score_seed_file(
        seed_file,
        build_upi_answers(upi_01="yes", upi_02="no", upi_03="no", upi_04="no"),
    )

    assert result.raw_score == 1
    assert result.risk_level is QuestionnaireRiskLevel.HIGH
    assert result.hard_trigger_hit is True
    assert result.hard_trigger_matches[0].question_code == "UPI_01"
    assert result.hard_trigger_matches[0].matched_value == "yes"
    assert result.hard_trigger_matches[0].reason_code == "HT-04"


def test_upi_hard_trigger_on_upi_02_upgrades_result_to_high() -> None:
    """UPI_02 = yes should also upgrade the auxiliary questionnaire to high risk."""
    service = QuestionnaireScoringService()
    seed_file = load_seed("UPI")

    result = service.score_seed_file(
        seed_file,
        build_upi_answers(upi_01="no", upi_02="yes", upi_03="no", upi_04="no"),
    )

    assert result.raw_score == 1
    assert result.risk_level is QuestionnaireRiskLevel.HIGH
    assert result.hard_trigger_hit is True
    assert result.hard_trigger_matches[0].question_code == "UPI_02"
    assert result.hard_trigger_matches[0].matched_value == "yes"
    assert result.hard_trigger_matches[0].reason_code == "HT-05"


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
