"""Service layer for administrator analytics chart data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from src.constants.account_enums import StudentRiskStatus
from src.constants.workflow_enums import AlertQueueStatus
from src.models.base import utc_now
from src.repositories.admin_analytics_repository import AdminAnalyticsRepository

DEFAULT_TREND_WINDOW_DAYS = 7
RISK_STATUS_ORDER = (
    StudentRiskStatus.NORMAL,
    StudentRiskStatus.WATCH,
    StudentRiskStatus.HIGH,
)
ALERT_QUEUE_STATUS_ORDER = (
    AlertQueueStatus.PENDING_REVIEW,
    AlertQueueStatus.CONFIRMED_PENDING_INTERVENTION,
    AlertQueueStatus.DISMISSED_FALSE_POSITIVE,
    AlertQueueStatus.CLOSED,
)


@dataclass(frozen=True, slots=True)
class AdminAnalyticsRiskDistributionItem:
    """One bucket in the student risk-distribution summary."""

    risk_status: StudentRiskStatus
    student_count: int


@dataclass(frozen=True, slots=True)
class AdminAnalyticsRiskDistributionSnapshot:
    """Chart-ready student risk-distribution payload."""

    total_students: int
    items: list[AdminAnalyticsRiskDistributionItem]


@dataclass(frozen=True, slots=True)
class AdminAnalyticsDailyTrendItem:
    """One point in the fixed recent-activity time series."""

    date: date
    questionnaire_submission_count: int
    treehole_post_count: int
    alert_case_count: int


@dataclass(frozen=True, slots=True)
class AdminAnalyticsDailyTrendSnapshot:
    """Recent activity series used by the analytics trend chart."""

    window_days: int
    start_date: date
    end_date: date
    items: list[AdminAnalyticsDailyTrendItem]


@dataclass(frozen=True, slots=True)
class AdminAnalyticsAlertProcessingItem:
    """One bucket in the alert-case processing summary."""

    queue_status: AlertQueueStatus
    case_count: int


@dataclass(frozen=True, slots=True)
class AdminAnalyticsAlertProcessingSnapshot:
    """Chart-ready alert workflow status summary."""

    total_alert_case_count: int
    items: list[AdminAnalyticsAlertProcessingItem]


@dataclass(frozen=True, slots=True)
class AdminAnalyticsSnapshot:
    """Complete analytics payload consumed by the admin chart page."""

    generated_at: datetime
    risk_distribution: AdminAnalyticsRiskDistributionSnapshot
    daily_trends: AdminAnalyticsDailyTrendSnapshot
    alert_processing: AdminAnalyticsAlertProcessingSnapshot


class AdminAnalyticsService:
    """Build the fixed analytics snapshot required by IMPLEMENTATION_PLAN 12.1."""

    def __init__(self, session: Session) -> None:
        self.repository = AdminAnalyticsRepository(session)

    def build_trends_snapshot(self) -> AdminAnalyticsSnapshot:
        """Return one chart-ready analytics snapshot for the admin backend."""
        generated_at = utc_now()
        end_date = generated_at.date()
        start_date = end_date - timedelta(days=DEFAULT_TREND_WINDOW_DAYS - 1)
        start_at = datetime.combine(start_date, time.min)
        end_before = datetime.combine(end_date + timedelta(days=1), time.min)

        risk_counts = self.repository.load_student_risk_distribution()
        alert_status_counts = self.repository.load_alert_queue_status_counts()
        submission_dates = self.repository.load_questionnaire_submission_dates(
            start_at=start_at,
            end_before=end_before,
        )
        treehole_dates = self.repository.load_treehole_post_dates(
            start_at=start_at,
            end_before=end_before,
        )
        alert_dates = self.repository.load_alert_case_dates(
            start_at=start_at,
            end_before=end_before,
        )

        risk_distribution_items = [
            AdminAnalyticsRiskDistributionItem(
                risk_status=risk_status,
                student_count=risk_counts.get(risk_status, 0),
            )
            for risk_status in RISK_STATUS_ORDER
        ]
        alert_processing_items = [
            AdminAnalyticsAlertProcessingItem(
                queue_status=queue_status,
                case_count=alert_status_counts.get(queue_status, 0),
            )
            for queue_status in ALERT_QUEUE_STATUS_ORDER
        ]

        return AdminAnalyticsSnapshot(
            generated_at=generated_at,
            risk_distribution=AdminAnalyticsRiskDistributionSnapshot(
                total_students=sum(item.student_count for item in risk_distribution_items),
                items=risk_distribution_items,
            ),
            daily_trends=AdminAnalyticsDailyTrendSnapshot(
                window_days=DEFAULT_TREND_WINDOW_DAYS,
                start_date=start_date,
                end_date=end_date,
                items=self._build_daily_trend_items(
                    start_date=start_date,
                    submission_dates=submission_dates,
                    treehole_dates=treehole_dates,
                    alert_dates=alert_dates,
                ),
            ),
            alert_processing=AdminAnalyticsAlertProcessingSnapshot(
                total_alert_case_count=sum(
                    item.case_count for item in alert_processing_items
                ),
                items=alert_processing_items,
            ),
        )

    def _build_daily_trend_items(
        self,
        *,
        start_date: date,
        submission_dates: list[date],
        treehole_dates: list[date],
        alert_dates: list[date],
    ) -> list[AdminAnalyticsDailyTrendItem]:
        """Return one zero-filled seven-day trend series ordered from old to new."""
        submission_counts = Counter(submission_dates)
        treehole_counts = Counter(treehole_dates)
        alert_counts = Counter(alert_dates)

        return [
            AdminAnalyticsDailyTrendItem(
                date=current_date,
                questionnaire_submission_count=submission_counts.get(current_date, 0),
                treehole_post_count=treehole_counts.get(current_date, 0),
                alert_case_count=alert_counts.get(current_date, 0),
            )
            for current_date in (
                start_date + timedelta(days=offset)
                for offset in range(DEFAULT_TREND_WINDOW_DAYS)
            )
        ]
