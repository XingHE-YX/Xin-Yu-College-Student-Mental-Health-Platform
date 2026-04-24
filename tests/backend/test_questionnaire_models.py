"""Tests for questionnaire-related ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from src.constants.questionnaire_enums import (
    AssessmentReportType,
    QuestionType,
    QuestionnaireCategory,
    QuestionnaireRiskLevel,
    QuestionnaireScoringMode,
    QuestionnaireSubmissionStatus,
)
from src.models import (
    AssessmentReport,
    Base,
    QuestionBank,
    QuestionnaireAnswer,
    QuestionnaireSubmission,
    QuestionnaireTemplate,
    StudentUser,
)


def test_questionnaire_tables_compile_to_mysql_contract() -> None:
    """The questionnaire models should compile to the expected MySQL schema."""
    template_sql = str(
        CreateTable(QuestionnaireTemplate.__table__).compile(dialect=mysql.dialect())
    )
    question_sql = str(CreateTable(QuestionBank.__table__).compile(dialect=mysql.dialect()))
    submission_sql = str(
        CreateTable(QuestionnaireSubmission.__table__).compile(dialect=mysql.dialect())
    )
    answer_sql = str(CreateTable(QuestionnaireAnswer.__table__).compile(dialect=mysql.dialect()))
    report_sql = str(CreateTable(AssessmentReport.__table__).compile(dialect=mysql.dialect()))

    assert "SMALLINT UNSIGNED NOT NULL" in template_sql
    assert "ENUM('required','optional')" in template_sql
    assert "ENUM('sum_1_5','sum_0_3','zung_standard','yes_no')" in template_sql
    assert "JSON NOT NULL" in question_sql
    assert "ENUM('single_choice','yes_no')" in question_sql
    assert "FOREIGN KEY(template_id) REFERENCES questionnaire_templates (id)" in question_sql
    assert "ENUM('submitted','scored')" in submission_sql
    assert "ENUM('low','watch','high')" in submission_sql
    assert "FOREIGN KEY(student_id) REFERENCES student_users (id)" in submission_sql
    assert "FOREIGN KEY(question_id) REFERENCES question_bank (id)" in answer_sql
    assert "ENUM('scale_result','full_profile')" in report_sql
    assert "FOREIGN KEY(student_id) REFERENCES student_users (id)" in report_sql


def test_questionnaire_seed_import_and_answer_persistence_work() -> None:
    """Templates, questions, submissions, answers, and reports should persist together."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            StudentUser.__table__,
            QuestionnaireTemplate.__table__,
            QuestionBank.__table__,
            QuestionnaireSubmission.__table__,
            QuestionnaireAnswer.__table__,
            AssessmentReport.__table__,
        ],
    )
    inspector = inspect(engine)

    template_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("questionnaire_templates")
    }
    question_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("question_bank")
    }
    submission_foreign_keys = inspector.get_foreign_keys("questionnaire_submissions")
    answer_foreign_keys = inspector.get_foreign_keys("questionnaire_answers")
    report_foreign_keys = inspector.get_foreign_keys("assessment_reports")

    assert ("code",) in template_unique_constraints
    assert ("question_code",) in question_unique_constraints
    assert sorted(foreign_key["referred_table"] for foreign_key in submission_foreign_keys) == [
        "questionnaire_templates",
        "student_users",
    ]
    assert sorted(foreign_key["referred_table"] for foreign_key in answer_foreign_keys) == [
        "question_bank",
        "questionnaire_submissions",
    ]
    assert report_foreign_keys[0]["referred_table"] == "student_users"

    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        student = StudentUser(
            phone_e164="+8613812345678",
            wechat_openid="wx-questionnaire-demo",
            display_nickname="问卷同学",
            display_avatar_seed="seed-questionnaire",
            college_name="计算机学院",
            class_name="2026级2班",
        )
        template = QuestionnaireTemplate(
            code="SCREEN",
            name="快速筛查",
            category=QuestionnaireCategory.REQUIRED,
            question_count=2,
            scoring_mode=QuestionnaireScoringMode.SUM_1_5,
            unlock_required=True,
            is_active=True,
        )
        session.add_all([student, template])
        session.flush()

        question_1 = QuestionBank(
            template_id=template.id,
            question_code="SCREEN_01",
            question_order=1,
            question_text="最近是否常感到紧张？",
            question_type=QuestionType.SINGLE_CHOICE,
            options_json=[
                {"value": "1", "label": "从不"},
                {"value": "5", "label": "总是"},
            ],
            score_mapping_json={"1": 1, "5": 5},
            reverse_scored=False,
            hard_trigger_rule_json={"threshold": 4},
            seed_source="screen_questions.json",
        )
        question_2 = QuestionBank(
            template_id=template.id,
            question_code="SCREEN_02",
            question_order=2,
            question_text="最近睡眠是否受影响？",
            question_type=QuestionType.SINGLE_CHOICE,
            options_json=[
                {"value": "1", "label": "没有"},
                {"value": "4", "label": "明显"},
            ],
            score_mapping_json={"1": 1, "4": 4},
            reverse_scored=False,
            hard_trigger_rule_json=None,
            seed_source="screen_questions.json",
        )
        session.add_all([question_1, question_2])
        session.flush()

        submission = QuestionnaireSubmission(
            student_id=student.id,
            template_id=template.id,
            started_at=now,
            submitted_at=now,
            status=QuestionnaireSubmissionStatus.SCORED,
            raw_score=9,
            standardized_score=None,
            risk_level=QuestionnaireRiskLevel.WATCH,
            hard_trigger_hit=False,
            scoring_snapshot_json={"answered": 2, "total_score": 9},
        )
        session.add(submission)
        session.flush()

        answer_1 = QuestionnaireAnswer(
            submission_id=submission.id,
            question_id=question_1.id,
            selected_option="5",
            raw_value="5",
            normalized_score=5,
        )
        answer_2 = QuestionnaireAnswer(
            submission_id=submission.id,
            question_id=question_2.id,
            selected_option="4",
            raw_value="4",
            normalized_score=4,
        )
        report = AssessmentReport(
            student_id=student.id,
            report_type=AssessmentReportType.SCALE_RESULT,
            report_version="v1.0",
            source_submission_ids_json=[submission.id],
            risk_level=QuestionnaireRiskLevel.WATCH,
            result_title="快速筛查结果",
            content_json={"summary": "存在需关注信号"},
        )
        session.add_all([answer_1, answer_2, report])
        session.flush()
        session.refresh(template)
        session.refresh(submission)
        session.refresh(student)

        assert template.code == "SCREEN"
        assert template.unlock_required is True
        assert len(template.questions) == 2
        assert submission.status is QuestionnaireSubmissionStatus.SCORED
        assert submission.template.code == "SCREEN"
        assert submission.student.id == student.id
        assert len(submission.answers) == 2
        assert {answer.question.question_code for answer in submission.answers} == {
            "SCREEN_01",
            "SCREEN_02",
        }
        assert report.source_submission_ids_json == [submission.id]
        assert report.student.id == student.id
        assert student.questionnaire_submissions[0].id == submission.id
        assert student.assessment_reports[0].id == report.id

    engine.dispose()
