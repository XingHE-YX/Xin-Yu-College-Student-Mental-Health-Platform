"""Pydantic schemas for question-bank seed files."""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from src.constants.questionnaire_enums import (
    QuestionnaireCategory,
    QuestionnaireScoringMode,
    QuestionType,
)


class QuestionOptionSeed(BaseModel):
    """A single renderable option inside a seeded question."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=128)


class HardTriggerRuleSeed(BaseModel):
    """A question-level hard-trigger rule used by later risk logic."""

    model_config = ConfigDict(extra="forbid")

    operator: Literal[">=", "=="]
    value: int | str
    risk_level: Literal["high"]
    reason_code: str = Field(min_length=1, max_length=64)


class QuestionnaireTemplateSeed(BaseModel):
    """Template-level metadata that maps to `questionnaire_templates`."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=1, max_length=128)
    category: QuestionnaireCategory
    question_count: int = Field(ge=1, le=200)
    scoring_mode: QuestionnaireScoringMode
    unlock_required: bool
    is_active: bool = True


class QuestionSeed(BaseModel):
    """A single question-bank entry sourced from a seed file."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]*_\d{2}$")
    question_text: str = Field(min_length=1)
    question_type: QuestionType
    options: list[QuestionOptionSeed] = Field(min_length=2)
    score_mapping: dict[str, int] = Field(min_length=2)
    reverse_scored: bool
    hard_trigger_rule: HardTriggerRuleSeed | None

    @field_validator("options")
    @classmethod
    def validate_unique_option_values(
        cls,
        options: list[QuestionOptionSeed],
    ) -> list[QuestionOptionSeed]:
        """Require each option value to be unique inside one question."""
        option_values = [option.value for option in options]
        if len(option_values) != len(set(option_values)):
            raise ValueError("options must use unique value keys")
        return options

    @model_validator(mode="after")
    def validate_question_contract(self) -> QuestionSeed:
        """Validate question-level consistency between options and scoring metadata."""
        option_values = {option.value for option in self.options}
        score_mapping_keys = set(self.score_mapping)

        if score_mapping_keys != option_values:
            raise ValueError("score_mapping keys must exactly match option values")

        if self.question_type is QuestionType.YES_NO:
            if option_values != {"yes", "no"}:
                raise ValueError(
                    "yes_no questions must use exactly 'yes' and 'no' options"
                )
            if self.reverse_scored:
                raise ValueError("yes_no questions cannot be reverse scored")

        if self.hard_trigger_rule is None:
            return self

        hard_trigger_value = self.hard_trigger_rule.value
        if self.question_type is QuestionType.YES_NO:
            if self.hard_trigger_rule.operator != "==":
                raise ValueError("yes_no hard triggers must use the '==' operator")
            if (
                not isinstance(hard_trigger_value, str)
                or hard_trigger_value not in option_values
            ):
                raise ValueError(
                    "yes_no hard triggers must compare against 'yes' or 'no'"
                )
            return self

        if self.hard_trigger_rule.operator == ">=":
            if not isinstance(hard_trigger_value, int):
                raise ValueError(
                    "single_choice '>=' hard triggers must use an integer threshold"
                )
            if hard_trigger_value > max(self.score_mapping.values()):
                raise ValueError(
                    "hard trigger threshold cannot exceed configured score values"
                )
            return self

        if (
            isinstance(hard_trigger_value, str)
            and hard_trigger_value not in option_values
        ):
            raise ValueError(
                "single_choice '==' hard triggers using strings must match option values"
            )
        if isinstance(hard_trigger_value, int) and hard_trigger_value not in set(
            self.score_mapping.values()
        ):
            raise ValueError(
                "single_choice '==' hard triggers using integers must match scores"
            )
        return self


class QuestionBankSeedFile(BaseModel):
    """A complete seed file containing one questionnaire template and its questions."""

    model_config = ConfigDict(extra="forbid")

    template: QuestionnaireTemplateSeed
    questions: list[QuestionSeed] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_seed_file_contract(self) -> QuestionBankSeedFile:
        """Validate file-level consistency across template metadata and question list."""
        if self.template.question_count != len(self.questions):
            raise ValueError(
                "template.question_count must match the number of questions"
            )

        question_ids = [question.question_id for question in self.questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("question_id values must be unique inside one seed file")

        template_prefix = f"{self.template.code}_"
        for index, question in enumerate(self.questions, start=1):
            if not question.question_id.startswith(template_prefix):
                raise ValueError(
                    f"question_id '{question.question_id}' must start with '{template_prefix}'"
                )
            suffix = question.question_id.removeprefix(template_prefix)
            if int(suffix) != index:
                raise ValueError(
                    "question_id numeric suffix must match the question order in the array"
                )

        return self

    @field_validator("questions")
    @classmethod
    def validate_questions_match_scoring_mode(
        cls,
        questions: list[QuestionSeed],
        info: ValidationInfo,
    ) -> list[QuestionSeed]:
        """Apply scoring-mode rules after the template field has been parsed."""
        template = info.data.get("template")
        if template is None:
            return questions

        for question in questions:
            if (
                template.scoring_mode is QuestionnaireScoringMode.YES_NO
                and question.question_type is not QuestionType.YES_NO
            ):
                raise ValueError(
                    "yes_no scoring_mode requires every question to use "
                    "question_type yes_no"
                )
            if (
                template.scoring_mode is QuestionnaireScoringMode.ZUNG_STANDARD
                and question.question_type is not QuestionType.SINGLE_CHOICE
            ):
                raise ValueError(
                    "zung_standard scoring_mode requires single_choice questions"
                )
        return questions
