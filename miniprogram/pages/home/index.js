const { PAGE_ROUTES } = require("../../constants/config");
const { getPrimaryChannelRoute } = require("../../constants/navigation");
const {
  getQuestionnaireRouteByCode,
} = require("../../constants/questionnaires");
const {
  fetchQuestionnaireList,
  fetchRequiredProgress,
} = require("../../services/questionnaires");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../utils/session");
const {
  switchToPrimaryTab,
} = require("../../utils/navigation");

const QUESTIONNAIRE_COPY = {
  SCREEN: {
    summary: "先用 15 道题快速了解最近一周的情绪、压力和精力状态。",
    helper: "建议作为主线第一步完成，后续四份必做问卷会按固定 70 题链路继续展开。",
    badge: "起点",
  },
  SDS: {
    summary: "20 道 SDS 题目聚焦抑郁相关体验，结果会进入完整画像报告。",
    helper: "建议在快速筛查后继续完成，帮助系统建立更完整的状态判断。",
    badge: "主线",
  },
  SAS: {
    summary: "20 道 SAS 题目帮助识别焦虑相关困扰，采用标准分换算。",
    helper: "与 SDS 一起构成核心情绪量表主线。",
    badge: "主线",
  },
  SLEEP: {
    summary: "15 道睡眠问卷聚焦入睡、醒来和恢复感，补齐作息维度。",
    helper: "完成后即可判断 70 题主线是否已满足完整报告解锁条件。",
    badge: "完成主线",
  },
  UPI: {
    summary: "4 道 UPI 辅助题用于补充识别风险信号，不阻塞完整报告解锁。",
    helper: "你可以任意时间主动完成，它只作为辅助参考。",
    badge: "可选",
  },
};

const RISK_LABELS = {
  low: "低风险",
  watch: "需关注",
  high: "高风险",
};

function buildFallbackProgress() {
  return {
    completed_required_questionnaires: 0,
    total_required_questionnaires: 4,
    completed_required_questions: 0,
    total_required_questions: 70,
    full_profile_unlocked: false,
    required_questionnaires: [],
  };
}

function buildMissingRequiredNames(progress) {
  if (!progress || !Array.isArray(progress.required_questionnaires)) {
    return [];
  }

  return progress.required_questionnaires
    .filter((item) => !item.completed)
    .map((item) => item.name);
}

function buildProgressHeadline(progress) {
  if (progress.full_profile_unlocked) {
    return "完整报告已达到查看条件";
  }
  if (progress.completed_required_questions <= 0) {
    return "先从快速筛查开始建立当前状态";
  }
  return `当前已完成 ${progress.completed_required_questions} / ${progress.total_required_questions} 题`;
}

function buildProgressSummary(progress) {
  if (progress.full_profile_unlocked) {
    return "四份必做问卷均已完成。你现在可以前往报告频道查看完整综合画像。";
  }

  const missingNames = buildMissingRequiredNames(progress);
  if (!missingNames.length) {
    return "主线问卷即将完成，提交最新结果后会自动刷新完整报告解锁状态。";
  }

  if (progress.completed_required_questions <= 0) {
    return "完成四份必做问卷后，完整报告会按固定 70 题链路自动解锁。";
  }

  return `剩余主线任务：${missingNames.join("、")}。每次提交后，报告频道都会自动同步最新进度。`;
}

function buildCardTone(isCompleted, isRequired) {
  if (isCompleted) {
    return "success";
  }
  return isRequired ? "warning" : "default";
}

function buildRiskChipClass(riskLevel) {
  if (riskLevel === "high") {
    return "chip--danger";
  }
  if (riskLevel === "watch") {
    return "chip--warm";
  }
  return "chip--success";
}

function buildQuestionnaireCards(questionnaires) {
  return questionnaires.map((questionnaire) => {
    const copy = QUESTIONNAIRE_COPY[questionnaire.code] || {
      summary: "问卷元数据已同步，可直接进入作答页。",
      helper: "提交后会自动刷新最新结果与整体进度。",
      badge: "问卷",
    };
    const latestSubmission = questionnaire.latest_submission;
    const isCompleted = Boolean(latestSubmission);
    const isRequired = questionnaire.category === "required";
    return {
      code: questionnaire.code,
      name: questionnaire.name,
      summary: copy.summary,
      helper: copy.helper,
      badge: copy.badge,
      questionCountLabel: `${questionnaire.question_count} 题`,
      stateLabel: isCompleted ? "已完成" : isRequired ? "待完成" : "可选",
      stateTone: buildCardTone(isCompleted, isRequired),
      chainLabel: isRequired ? "70 题主线" : "辅助参考",
      latestResultLabel: latestSubmission
        ? `最近结果：${RISK_LABELS[latestSubmission.risk_level] || "已保存"}`
        : "",
      latestResultTone: latestSubmission
        ? buildRiskChipClass(latestSubmission.risk_level)
        : "",
      flowStepLabel: questionnaire.flow_step || "",
      isCompleted,
      isRequired,
    };
  });
}

function buildQuickActions(progress, questionnaires) {
  const nextRequired = questionnaires.find(
    (item) => item.isRequired && !item.isCompleted
  );
  const optionalUpi = questionnaires.find((item) => item.code === "UPI");

  return [
    {
      key: nextRequired ? `questionnaire:${nextRequired.code}` : "report",
      badge: nextRequired ? "继续" : "查看",
      title: nextRequired ? nextRequired.name : "完整报告",
      summary: nextRequired
        ? "继续主线任务，刷新完整报告解锁进度。"
        : "四份主线问卷已完成，可直接查看完整综合画像。",
    },
    {
      key: "report",
      badge: "报告",
      title: "报告频道",
      summary: progress.full_profile_unlocked
        ? "查看当前摘要与完整综合画像。"
        : "随时查看锁定状态、已完成结果和下一步建议。",
    },
    {
      key: optionalUpi ? `questionnaire:${optionalUpi.code}` : "help",
      badge: optionalUpi && !optionalUpi.isCompleted ? "可选" : "帮助",
      title:
        optionalUpi && !optionalUpi.isCompleted ? "UPI 辅助筛查" : "帮助资源",
      summary:
        optionalUpi && !optionalUpi.isCompleted
          ? "不阻塞主线解锁，但可补充辅助风险信号。"
          : "查看热线、校内资源和冷静处理建议。",
    },
    {
      key: "treehole",
      badge: "树洞",
      title: "匿名广场",
      summary: "如你已经开放授权，也可以去树洞频道写下当下心情。",
    },
  ];
}

function splitQuestionnaireGroups(questionnaires) {
  return {
    requiredCards: questionnaires.filter((item) => item.isRequired),
    optionalCards: questionnaires.filter((item) => !item.isRequired),
  };
}

Page({
  data: {
    student: null,
    consentDeclined: false,
    requiredProgress: buildFallbackProgress(),
    progressHeadline: buildProgressHeadline(buildFallbackProgress()),
    progressSummary: buildProgressSummary(buildFallbackProgress()),
    missingRequiredNames: [],
    requiredCards: [],
    optionalCards: [],
    quickActions: [],
    loadingDashboard: true,
    dashboardError: "",
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

  bootstrap(options = {}) {
    const preserveContent = Boolean(options.preserveContent);
    try {
      const session = loadStudentSession();
      if (!hasValidStudentSession(session)) {
        clearStudentSession();
        wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
        return;
      }

      getApp().globalData.studentSession = session;
      if (session.student.consent_status === "missing") {
        wx.reLaunch({ url: PAGE_ROUTES.CONSENT });
        return;
      }

      const nextState = {
        student: session.student,
        consentDeclined: session.student.consent_status === "declined",
        loadingDashboard: preserveContent
          ? this.data.loadingDashboard
          : true,
        dashboardError: "",
      };

      if (!preserveContent) {
        const fallbackProgress = buildFallbackProgress();
        Object.assign(nextState, {
          requiredProgress: fallbackProgress,
          progressHeadline: buildProgressHeadline(fallbackProgress),
          progressSummary: buildProgressSummary(fallbackProgress),
          missingRequiredNames: [],
          requiredCards: [],
          optionalCards: [],
          quickActions: buildQuickActions(fallbackProgress, []),
        });
      }

      this.setData(nextState);
      this.hasBootstrapped = true;
      this.loadDashboardData(session);
    } catch (error) {
      clearStudentSession();
      wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
    }
  },

  loadDashboardData(session) {
    Promise.all([
      fetchQuestionnaireList({ accessToken: session.accessToken }),
      fetchRequiredProgress({ accessToken: session.accessToken }),
    ])
      .then(([questionnaireData, progressData]) => {
        const progress = progressData.progress || buildFallbackProgress();
        const questionnaires = buildQuestionnaireCards(
          questionnaireData.questionnaires || []
        );
        const { requiredCards, optionalCards } =
          splitQuestionnaireGroups(questionnaires);
        this.setData({
          requiredProgress: progress,
          progressHeadline: buildProgressHeadline(progress),
          progressSummary: buildProgressSummary(progress),
          missingRequiredNames: buildMissingRequiredNames(progress),
          requiredCards,
          optionalCards,
          quickActions: buildQuickActions(progress, questionnaires),
          loadingDashboard: false,
          dashboardError: "",
        });
      })
      .catch((error) => {
        if (error && error.statusCode === 401) {
          clearStudentSession();
          wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
          return;
        }

        const fallbackProgress = buildFallbackProgress();
        this.setData({
          requiredProgress: fallbackProgress,
          progressHeadline: buildProgressHeadline(fallbackProgress),
          progressSummary:
            "问卷目录暂时未能同步。你仍可以稍后重试，或先前往其他频道。",
          missingRequiredNames: [],
          requiredCards: [],
          optionalCards: [],
          quickActions: buildQuickActions(fallbackProgress, []),
          loadingDashboard: false,
          dashboardError:
            (error && error.message) || "问卷目录加载失败，请稍后重试。",
        });
      });
  },

  handleRetryTap() {
    const session = loadStudentSession();
    if (!hasValidStudentSession(session)) {
      clearStudentSession();
      wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
      return;
    }

    this.setData({
      loadingDashboard: true,
      dashboardError: "",
    });
    this.loadDashboardData(session);
  },

  handleQuestionnaireTap(event) {
    const { code } = event.currentTarget.dataset;
    if (this.data.loadingDashboard) {
      wx.showToast({
        title: "问卷目录同步中",
        icon: "none",
      });
      return;
    }

    const route = getQuestionnaireRouteByCode(code);
    if (!route) {
      wx.showToast({
        title: "该问卷入口暂不可用",
        icon: "none",
      });
      return;
    }

    wx.navigateTo({ url: route });
  },

  handleQuickAction(event) {
    const { key } = event.detail || {};
    if (!key) {
      return;
    }

    if (key.startsWith("questionnaire:")) {
      const code = key.split(":")[1];
      const route = getQuestionnaireRouteByCode(code);
      if (route) {
        wx.navigateTo({ url: route });
      }
      return;
    }

    if (key === "report") {
      switchToPrimaryTab(PAGE_ROUTES.REPORT_SUMMARY);
      return;
    }

    if (key === "treehole") {
      switchToPrimaryTab(PAGE_ROUTES.TREEHOLE_FEED);
      return;
    }

    if (key === "help") {
      wx.navigateTo({ url: PAGE_ROUTES.HELP });
    }
  },

  handleChannelChange(event) {
    const { key } = event.detail || {};
    const route = getPrimaryChannelRoute(key);
    if (!route || route === PAGE_ROUTES.HOME) {
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
      tabBar.setActiveByRoute(PAGE_ROUTES.HOME);
    }
  },
});
