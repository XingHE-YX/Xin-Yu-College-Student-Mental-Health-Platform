const { HOTLINE_PHONE, PAGE_ROUTES } = require("../../../constants/config");
const { fetchFullReport } = require("../../../services/reports");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../../utils/session");
const {
  redirectOrSwitchTab,
  switchToPrimaryTab,
} = require("../../../utils/navigation");

function ensureAuthenticatedSession(pageInstance) {
  const session = loadStudentSession();
  if (!hasValidStudentSession(session)) {
    clearStudentSession();
    wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
    return null;
  }

  getApp().globalData.studentSession = session;
  if (session.student.consent_status === "missing") {
    wx.reLaunch({ url: PAGE_ROUTES.CONSENT });
    return null;
  }

  if (pageInstance) {
    pageInstance.setData({
      student: session.student,
    });
  }
  return session;
}

function joinScoreSummary(scoreSummary) {
  if (!Array.isArray(scoreSummary) || !scoreSummary.length) {
    return "";
  }

  return scoreSummary
    .map((item) => `${item.label} ${item.value}`)
    .join(" · ");
}

Page({
  data: {
    student: null,
    hotlinePhone: HOTLINE_PHONE,
    loading: true,
    loadError: "",
    hero: null,
    resultBadge: null,
    unlockStatus: null,
    integratedSummary: "",
    questionnaireSummaries: [],
    trendPlaceholder: null,
    recommendations: [],
    disclaimer: "",
    safetyBanner: null,
  },

  onLoad() {
    this.bootstrap();
  },

  onPullDownRefresh() {
    this.bootstrap();
  },

  bootstrap() {
    const session = ensureAuthenticatedSession(this);
    if (!session) {
      wx.stopPullDownRefresh();
      return;
    }

    this.setData({
      loading: true,
      loadError: "",
    });

    fetchFullReport({ accessToken: session.accessToken })
      .then((response) => {
        const report = response.report;
        const content = report.content || {};
        this.setData({
          loading: false,
          loadError: "",
          hero: content.hero_card || null,
          resultBadge: content.result_badge || null,
          unlockStatus: content.unlock_status || null,
          integratedSummary: content.integrated_summary || "",
          questionnaireSummaries: (content.questionnaire_summaries || []).map(
            (item) => ({
              name: item.questionnaire.name,
              code: item.questionnaire.code,
              riskLabel: item.result_badge.label,
              riskTone: item.result_badge.risk_level,
              scoreSummaryText: joinScoreSummary(item.score_summary),
              summaryText: item.summary_text,
              hardTriggerHit: Boolean(item.hard_trigger_hit),
            })
          ),
          trendPlaceholder: content.trend_placeholder || null,
          recommendations: content.recommendations || [],
          disclaimer: content.disclaimer || "",
          safetyBanner: content.safety_banner || null,
        });
      })
      .catch((error) => {
        if (error && error.statusCode === 401) {
          clearStudentSession();
          wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
          return;
        }

        if (error && error.code === "FULL_PROFILE_LOCKED") {
          wx.showToast({
            title: "完整报告尚未解锁",
            icon: "none",
          });
          redirectOrSwitchTab(PAGE_ROUTES.REPORT_SUMMARY);
          return;
        }

        this.setData({
          loading: false,
          loadError:
            (error && error.message) || "完整报告加载失败，请稍后重试。",
        });
      })
      .finally(() => {
        wx.stopPullDownRefresh();
      });
  },

  handleRetryLoad() {
    this.bootstrap();
  },

  handleBackSummary() {
    wx.navigateBack({
      fail() {
        switchToPrimaryTab(PAGE_ROUTES.REPORT_SUMMARY);
      },
    });
  },

  handleBackHome() {
    switchToPrimaryTab(PAGE_ROUTES.HOME);
  },
});
