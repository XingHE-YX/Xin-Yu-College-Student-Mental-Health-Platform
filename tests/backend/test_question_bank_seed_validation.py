"""Tests for question-bank seed-file validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from src.utils.validate_question_bank_seeds import (
    discover_seed_files,
    load_seed_file,
    validate_seed_files,
)


def write_seed_file(path: Path, payload: dict) -> None:
    """Persist one JSON seed payload for validation tests."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_valid_seed_payload() -> dict:
    """Build a valid seed payload that follows the unified structure."""
    return {
        "template": {
            "code": "SCREEN",
            "name": "快速筛查",
            "category": "required",
            "question_count": 2,
            "scoring_mode": "sum_1_5",
            "unlock_required": True,
            "is_active": True,
        },
        "questions": [
            {
                "question_id": "SCREEN_01",
                "question_text": "最近一周，你是否经常感到紧张？",
                "question_type": "single_choice",
                "options": [
                    {"value": "1", "label": "从不"},
                    {"value": "5", "label": "总是"},
                ],
                "score_mapping": {"1": 1, "5": 5},
                "reverse_scored": False,
                "hard_trigger_rule": None,
            },
            {
                "question_id": "SCREEN_02",
                "question_text": "最近一周，你是否觉得休息后仍很累？",
                "question_type": "single_choice",
                "options": [
                    {"value": "1", "label": "没有"},
                    {"value": "4", "label": "明显"},
                ],
                "score_mapping": {"1": 1, "4": 4},
                "reverse_scored": False,
                "hard_trigger_rule": {
                    "operator": ">=",
                    "value": 4,
                    "risk_level": "high",
                    "reason_code": "HT-01",
                },
            },
        ],
    }


def test_load_seed_file_accepts_valid_seed_payload(tmp_path: Path) -> None:
    """A valid seed file should parse into the unified template/question structure."""
    seed_path = tmp_path / "screen_questions.json"
    write_seed_file(seed_path, build_valid_seed_payload())

    seed_file = load_seed_file(seed_path)

    assert seed_file.template.code == "SCREEN"
    assert seed_file.template.question_count == 2
    assert len(seed_file.questions) == 2
    assert seed_file.questions[1].hard_trigger_rule is not None
    assert seed_file.questions[1].hard_trigger_rule.reason_code == "HT-01"


def test_load_seed_file_rejects_question_count_mismatch(tmp_path: Path) -> None:
    """Template question_count must equal the number of question entries."""
    seed_path = tmp_path / "screen_questions.json"
    payload = build_valid_seed_payload()
    payload["template"]["question_count"] = 3
    write_seed_file(seed_path, payload)

    with pytest.raises(ValidationError, match="question_count"):
        load_seed_file(seed_path)


def test_load_seed_file_rejects_invalid_yes_no_trigger_rule(tmp_path: Path) -> None:
    """Yes/no questions must use 'yes' and 'no' with an equality trigger."""
    seed_path = tmp_path / "upi_questions.json"
    payload = {
        "template": {
            "code": "UPI",
            "name": "UPI 辅助筛查",
            "category": "optional",
            "question_count": 1,
            "scoring_mode": "yes_no",
            "unlock_required": False,
            "is_active": True,
        },
        "questions": [
            {
                "question_id": "UPI_01",
                "question_text": "你是否曾反复出现明确轻生想法？",
                "question_type": "yes_no",
                "options": [
                    {"value": "yes", "label": "是"},
                    {"value": "no", "label": "否"},
                ],
                "score_mapping": {"yes": 1, "no": 0},
                "reverse_scored": False,
                "hard_trigger_rule": {
                    "operator": ">=",
                    "value": 1,
                    "risk_level": "high",
                    "reason_code": "HT-04",
                },
            }
        ],
    }
    write_seed_file(seed_path, payload)

    with pytest.raises(ValidationError, match="yes_no hard triggers"):
        load_seed_file(seed_path)


def test_discover_and_validate_seed_files_in_directory(tmp_path: Path) -> None:
    """Directory validation should collect all JSON files in sorted order."""
    screen_path = tmp_path / "screen_questions.json"
    upi_path = tmp_path / "upi_questions.json"
    write_seed_file(screen_path, build_valid_seed_payload())
    write_seed_file(
        upi_path,
        {
            "template": {
                "code": "UPI",
                "name": "UPI 辅助筛查",
                "category": "optional",
                "question_count": 1,
                "scoring_mode": "yes_no",
                "unlock_required": False,
                "is_active": True,
            },
            "questions": [
                {
                    "question_id": "UPI_01",
                    "question_text": "你是否曾反复出现明确轻生想法？",
                    "question_type": "yes_no",
                    "options": [
                        {"value": "yes", "label": "是"},
                        {"value": "no", "label": "否"},
                    ],
                    "score_mapping": {"yes": 1, "no": 0},
                    "reverse_scored": False,
                    "hard_trigger_rule": {
                        "operator": "==",
                        "value": "yes",
                        "risk_level": "high",
                        "reason_code": "HT-04",
                    },
                }
            ],
        },
    )

    discovered_paths = discover_seed_files(tmp_path)
    validated_files = validate_seed_files(discovered_paths)

    assert discovered_paths == [screen_path, upi_path]
    assert [seed_file.template.code for seed_file in validated_files] == [
        "SCREEN",
        "UPI",
    ]
