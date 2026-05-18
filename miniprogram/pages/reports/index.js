const { HOTLINE_PHONE, PAGE_ROUTES } = require("../../constants/config");
const { getPrimaryChannelRoute } = require("../../constants/navigation");
const { getQuestionnaireRouteByCode } = require("../../constants/questionnaires");
const {
  fetchReportHistory,
  fetchReportSummary,
} = require("../../services/reports");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../utils/session");
const {
  switchToPrimaryTab,
} = require("../../utils/navigation");
const {
  readChannelCache,
  shouldRefreshChannel,
  writeChannelCache,
} = require("../../utils/channel-sync");

function buildFallbackSummary() {
  return {
    state: "locked",
    hero_card: {
      eyebrow: "我的报告",
      title: "完成 70 道必做题后可查看完整报告",
      summary: "建议先从快速筛查开始，系统会在每次提交后自动更新进度与单量表结果。",
      surface_tone: "brand",
    },
    progress: {
      required_questions_completed: 0,
      required_questions_total: 70,
      required_questionnaires_completed: 0,
      required_questionnaires_total: 4,
      full_profile_unlocked: false,
      missing_required_questionnaires: [],
    },
    scale_results: [],
    next_actions: [],
    disclaimer: "本结果用于自助筛查与校园支持参考，不构成诊断。",
  };
}

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

function formatSubmittedAt(value) {
  if (!value || typeof value !== "string") {
    return "";
  }
  const normalized = value.replace("T", " ");
  return normalized.slice(0, 16);
}

function joinScoreSummary(scoreSummary) {
  if (!Array.isArray(scoreSummary) || !scoreSummary.length) {
    return "";
  }

  return scoreSummary
    .map((item) => `${item.label} ${item.value}`)
    .join(" · ");
}

function mapAction(action) {
  let route = "";
  let mode = "navigateTo";
  let available = true;
  if (action.target_questionnaire_code) {
    route = getQuestionnaireRouteByCode(action.target_questionnaire_code);
    available = Boolean(route);
  } else if (action.flow_step === "S10A") {
    route = PAGE_ROUTES.REPORT_FULL;
  } else if (action.flow_step === "S15") {
    route = PAGE_ROUTES.HELP;
  } else {
    available = false;
  }

  return {
    label: action.label,
    buttonVariant: action.button_variant,
    route,
    mode,
    available,
  };
}

function mapScaleResultCard(item) {
  return {
    code: item.questionnaire.code,
    name: item.questionnaire.name,
    submittedAtLabel: formatSubmittedAt(item.submitted_at),
    riskLabel: item.result_badge.label,
    riskTone: item.result_badge.risk_level,
    scoreSummaryText: joinScoreSummary(item.score_summary),
    summaryText: item.summary_text,
    hardTriggerHit: Boolean(item.hard_trigger_hit),
  };
}

function mapHistoryRecord(item) {
  return {
    code: item.questionnaire_code,
    name: item.questionnaire_name,
    submittedAtLabel: formatSubmittedAt(item.submitted_at),
    riskLabel: item.risk_level === "low" ? "低风险" : item.risk_level === "watch" ? "需关注" : "高风险",
    riskTone: item.risk_level,
    resultTitle: item.result_title,
    scoreSummaryText: joinScoreSummary(item.score_summary),
    summaryText: item.summary_text,
    hardTriggerHit: item.hard_trigger_hit,
  };
}

function buildSummaryHeadline(summaryState, progress) {
  if (summaryState === "unlocked") {
    return "完整报告已解锁";
  }
  if (summaryState === "partial") {
    return `已完成 ${progress.required_questions_completed} / ${progress.required_questions_total} 题`;
  }
  return "完整报告仍处于锁定状态";
}

function buildSummaryText(summaryState) {
  if (summaryState === "unlocked") {
    return "你已经完成四份必做问卷。现在可以先看摘要，也可以直接进入完整综合画像页。";
  }
  if (summaryState === "partial") {
    return "你已经完成了部分量表，当前摘要和最近结果会先展示在这里。";
  }
  return "当前还没有完整的量表结果，先从快速筛查开始即可。";
}

function buildReportStateFromPayload(payload) {
  const summary = payload.summary || buildFallbackSummary();
  const progress = summary.progress || buildFallbackSummary().progress;

  return {
    loading: false,
    loadError: "",
    hero: summary.hero_card || buildFallbackSummary().hero_card,
    overviewBadge: summary.overview_badge || null,
    progress,
    scaleResults: (summary.scale_results || []).map(mapScaleResultCard),
    nextActions: (summary.next_actions || []).map(mapAction),
    historyRecords: (payload.historyRecords || []).map(mapHistoryRecord),
    disclaimer: summary.disclaimer || buildFallbackSummary().disclaimer,
    safetyBanner: summary.safety_banner || null,
    summaryState: summary.state || "locked",
    summaryHeadline: buildSummaryHeadline(summary.state || "locked", progress),
    summaryBody: buildSummaryText(summary.state || "locked"),
    missingRequiredNames: (progress.missing_required_questionnaires || []).map(
      (item) => item.name
    ),
  };
}

Page({
  data: {
    student: null,
    hotlinePhone: HOTLINE_PHONE,
    loading: true,
    loadError: "",
    hero: buildFallbackSummary().hero_card,
    overviewBadge: null,
    progress: buildFallbackSummary().progress,
    scaleResults: [],
    nextActions: [],
    historyRecords: [],
    disclaimer: buildFallbackSummary().disclaimer,
    safetyBanner: null,
    summaryState: "locked",
    missingRequiredNames: [],
    summaryHeadline: buildSummaryHeadline(
      "locked",
      buildFallbackSummary().progress
    ),
    summaryBody: buildSummaryText("locked"),
  },

  onLoad() {
    this.skipNextOnShowRefresh = true;
    this.bootstrap();
  },

  onShow() {
    this.syncPrimaryTabBar();
    if (this.skipNextOnShowRefresh) {
      this.skipNextOnShowRefresh = false;
      return;
    }
    if (this.hasBootstrapped) {
      this.bootstrap({ preserveContent: true });
    }
  },

  onUnload() {
    this.latestReportRequestId = (this.latestReportRequestId || 0) + 1;
  },

  onPullDownRefresh() {
    this.bootstrap();
  },

  bootstrap(options = {}) {
    const preserveContent = Boolean(options.preserveContent);
    const session = ensureAuthenticatedSession(this);
    if (!session) {
      wx.stopPullDownRefresh();
      return;
    }

    const shouldRefresh = shouldRefreshChannel("report", {
      force: options.forceRefresh === true || !preserveContent,
    });
    const cachedPayload = preserveContent ? readChannelCache("report") : null;

    if (cachedPayload) {
      this.setData({
        ...buildReportStateFromPayload(cachedPayload),
        student: session.student,
      });
    } else {
      this.setData(
        preserveContent
          ? {
              loadError: "",
            }
          : {
              loading: true,
              loadError: "",
            }
      );
    }
    this.hasBootstrapped = true;
    if (!shouldRefresh) {
      wx.stopPullDownRefresh();
      return;
    }

    const requestId = (this.latestReportRequestId || 0) + 1;
    this.latestReportRequestId = requestId;

    Promise.all([
      fetchReportSummary({ accessToken: session.accessToken }),
      fetchReportHistory({ accessToken: session.accessToken }).catch(() => ({
        records: [],
      })),
    ])
      .then(([summaryResponse, historyResponse]) => {
        if (requestId !== this.latestReportRequestId) {
          return;
        }
        const payload = {
          summary: summaryResponse.summary || buildFallbackSummary(),
          historyRecords: historyResponse.records || [],
        };
        writeChannelCache("report", payload);
        this.setData(buildReportStateFromPayload(payload));
      })
      .catch((error) => {
        if (requestId !== this.latestReportRequestId) {
          return;
        }
        if (error && error.statusCode === 401) {
          clearStudentSession();
          wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
          return;
        }

        this.setData({
          loading: false,
          loadError:
            (error && error.message) || "报告页加载失败，请稍后重试。",
        });
      })
      .finally(() => {
        wx.stopPullDownRefresh();
      });
  },

  handleRetryLoad() {
    this.bootstrap();
  },

  handleActionTap(event) {
    const index = Number(event.currentTarget.dataset.index);
    const action = this.data.nextActions[index];
    if (!action) {
      return;
    }

    if (!action.available || !action.route) {
      wx.showToast({
        title: "该入口将在后续步骤接入",
        icon: "none",
      });
      return;
    }

    if (action.mode === "reLaunch") {
      wx.reLaunch({ url: action.route });
      return;
    }

    wx.navigateTo({ url: action.route });
  },

  handleBackHome() {
    switchToPrimaryTab(PAGE_ROUTES.HOME);
  },

  handleChannelChange(event) {
    const { key } = event.detail || {};
    const route = getPrimaryChannelRoute(key);
    if (!route || route === PAGE_ROUTES.REPORT_SUMMARY) {
      return;
    }
    switchToPrimaryTab(route);
  },

  syncPrimaryTabBar() {
    if (typeof this.getTabBar !== "function") {
      return;
    }
    const tabBar = this.getTabBar();
    if (tabBar && typeof tabBar.setActiveByRoute === "function") {
      tabBar.setActiveByRoute(PAGE_ROUTES.REPORT_SUMMARY);
    }
  },
});
