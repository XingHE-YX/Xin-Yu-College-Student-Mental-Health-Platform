"""Tests for admin analytics view data-mapping helpers."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from admin.app import (  # noqa: E402
    build_alert_processing_chart_rows,
    build_analytics_summary_cards,
    build_daily_trend_chart_rows,
    build_daily_trend_peak_summary,
    build_daily_trend_table_rows,
    build_risk_distribution_chart_rows,
    summarize_daily_trends,
)


def test_build_risk_distribution_chart_rows_localizes_and_preserves_order() -> None:
    """Risk-distribution helpers should keep backend order and localized labels."""
    risk_distribution = {
        "total_students": 4,
        "items": [
            {"risk_status": "normal", "student_count": 1},
            {"risk_status": "watch", "student_count": 1},
            {"risk_status": "high", "student_count": 2},
        ],
    }

    rows = build_risk_distribution_chart_rows(risk_distribution)

    assert rows == [
        {
            "risk_status": "normal",
            "label": "正常",
            "student_count": 1,
            "tone": "success",
        },
        {
            "risk_status": "watch",
            "label": "需关注",
            "student_count": 1,
            "tone": "warning",
        },
        {
            "risk_status": "high",
            "label": "高风险",
            "student_count": 2,
            "tone": "danger",
        },
    ]


def test_build_alert_processing_chart_rows_localizes_and_applies_tones() -> None:
    """Alert-processing helpers should expose chart-ready labels and semantic tones."""
    alert_processing = {
        "total_alert_case_count": 5,
        "items": [
            {"queue_status": "pending_review", "case_count": 2},
            {"queue_status": "confirmed_pending_intervention", "case_count": 1},
            {"queue_status": "dismissed_false_positive", "case_count": 1},
            {"queue_status": "closed", "case_count": 1},
        ],
    }

    rows = build_alert_processing_chart_rows(alert_processing)

    assert rows == [
        {
            "queue_status": "pending_review",
            "label": "待复核",
            "case_count": 2,
            "tone": "warning",
        },
        {
            "queue_status": "confirmed_pending_intervention",
            "label": "已确认",
            "case_count": 1,
            "tone": "danger",
        },
        {
            "queue_status": "dismissed_false_positive",
            "label": "已忽略",
            "case_count": 1,
            "tone": "neutral",
        },
        {
            "queue_status": "closed",
            "label": "已结案",
            "case_count": 1,
            "tone": "brand",
        },
    ]


def test_build_daily_trend_helpers_keep_exact_counts_and_summary() -> None:
    """Daily-trend helpers should preserve backend counts for charts, tables, and KPIs."""
    analytics = {
        "risk_distribution": {
            "total_students": 4,
            "items": [
                {"risk_status": "normal", "student_count": 1},
                {"risk_status": "watch", "student_count": 1},
                {"risk_status": "high", "student_count": 2},
            ],
        },
        "daily_trends": {
            "window_days": 7,
            "start_date": "2026-04-23",
            "end_date": "2026-04-29",
            "items": [
                {
                    "date": "2026-04-23",
                    "questionnaire_submission_count": 1,
                    "treehole_post_count": 1,
                    "alert_case_count": 1,
                },
                {
                    "date": "2026-04-29",
                    "questionnaire_submission_count": 2,
                    "treehole_post_count": 1,
                    "alert_case_count": 3,
                },
            ],
        },
    }

    chart_rows = build_daily_trend_chart_rows(analytics["daily_trends"])
    table_rows = build_daily_trend_table_rows(analytics["daily_trends"])
    totals = summarize_daily_trends(analytics["daily_trends"])
    peak = build_daily_trend_peak_summary(analytics["daily_trends"])
    summary_cards = build_analytics_summary_cards(analytics)

    assert chart_rows == [
        {
            "date": "2026-04-23",
            "date_label": "04-23",
            "metric_label": "问卷提交",
            "count": 1,
        },
        {
            "date": "2026-04-23",
            "date_label": "04-23",
            "metric_label": "树洞发帖",
            "count": 1,
        },
        {
            "date": "2026-04-23",
            "date_label": "04-23",
            "metric_label": "新建工单",
            "count": 1,
        },
        {
            "date": "2026-04-29",
            "date_label": "04-29",
            "metric_label": "问卷提交",
            "count": 2,
        },
        {
            "date": "2026-04-29",
            "date_label": "04-29",
            "metric_label": "树洞发帖",
            "count": 1,
        },
        {
            "date": "2026-04-29",
            "date_label": "04-29",
            "metric_label": "新建工单",
            "count": 3,
        },
    ]
    assert table_rows == [
        {
            "日期": "2026-04-23",
            "问卷提交": 1,
            "树洞发帖": 1,
            "新建工单": 1,
        },
        {
            "日期": "2026-04-29",
            "问卷提交": 2,
            "树洞发帖": 1,
            "新建工单": 3,
        },
    ]
    assert totals == {
        "questionnaire_submission_count": 3,
        "treehole_post_count": 2,
        "alert_case_count": 4,
    }
    assert peak == {"date_label": "04-29", "total_count": 6}
    assert summary_cards == (
        (4, "在册学生数", "按当前 `student_users.risk_status` 聚合"),
        (3, "7 天量表提交", "窗口 2026-04-23 - 2026-04-29"),
        (2, "7 天树洞发帖", "按 `treehole_posts.created_at` 统计"),
        (4, "7 天新建工单", "按 `alert_cases.created_at` 统计"),
    )
