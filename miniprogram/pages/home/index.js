const { PAGE_ROUTES } = require("../../constants/config");
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

const QUESTIONNAIRE_COPY = {
  SCREEN: {
    summary: "先用 15 道题快速了解最近一周的情绪、压力和精力状态。",
    helper: "建议作为首个入口完成，后续必做量表会按固定 70 题链路继续展开。",
  },
  SDS: {
    summary: "20 道 SDS 题目聚焦抑郁相关体验，结果会进入完整画像报告。",
    helper: "完成后会与快速筛查、SAS 和睡眠问卷一起参与完整报告解锁。",
  },
  SAS: {
    summary: "20 道 SAS 题目帮助识别焦虑相关困扰，采用标准分换算。",
    helper: "建议在完成 SDS 后继续作答，保持同一阶段体验的一致性。",
  },
  SLEEP: {
    summary: "15 道睡眠问卷聚焦入睡、醒来和作息恢复情况。",
    helper: "睡眠结果会与情绪量表一起汇总到综合画像中。",
  },
  UPI: {
    summary: "4 道 UPI 辅助题用于补充识别风险信号，不阻塞完整报告解锁。",
    helper: "可在任意时间主动完成，结果仅作为辅助参考和风险升级信号。",
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

function buildProgressTitle(progress) {
  if (progress.full_profile_unlocked) {
    return "完整报告已达到解锁条件";
  }
  return "完整报告仍需完成必做问卷";
}

function buildMissingRequiredNames(progress) {
  if (!progress || !Array.isArray(progress.required_questionnaires)) {
    return [];
  }

  return progress.required_questionnaires
    .filter((item) => !item.completed)
    .map((item) => item.name);
}

function buildProgressSummary(progress) {
  if (progress.full_profile_unlocked) {
    return "四份必做问卷均已完成，后续可直接查看完整综合画像报告。";
  }

  const missingNames = buildMissingRequiredNames(progress);
  if (progress.completed_required_questions <= 0) {
    return "先从快速筛查开始。完成四份必做问卷后，完整报告会按固定 70 题链路自动解锁。";
  }

  if (missingNames.length) {
    return `当前已完成 ${progress.completed_required_questions} / ${progress.total_required_questions} 题，还差 ${missingNames.join("、")}。`;
  }

  return `当前已完成 ${progress.completed_required_questions} / ${progress.total_required_questions} 题，剩余必做问卷完成后即可解锁完整报告。`;
}

function buildMetaToneClass(tone) {
  if (tone === "warning") {
    return "module-card__meta--warning";
  }
  if (tone === "success") {
    return "module-card__meta--success";
  }
  if (tone === "disabled") {
    return "module-card__meta--disabled";
  }
  return "";
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
      summary: "问卷元数据已同步，可在后续步骤进入正式作答页。",
      helper: "当前阶段已接通目录和详情接口，提交流程将在后续步骤开放。",
    };
    const latestSubmission = questionnaire.latest_submission;
    const isCompleted = Boolean(latestSubmission);
    const isRequired = questionnaire.category === "required";

    return {
      code: questionnaire.code,
      name: questionnaire.name,
      flowStepLabel: questionnaire.flow_step
        ? `${questionnaire.flow_step} 问卷入口`
        : "问卷入口",
      statusLabel: isCompleted ? "已完成" : isRequired ? "待完成" : "可选",
      metaToneClass: buildMetaToneClass(
        isCompleted ? "success" : isRequired ? "warning" : "default"
      ),
      categoryLabel: isRequired ? "必做" : "可选",
      categoryChipClass: isRequired ? "" : "chip--warm",
      questionCountLabel: `${questionnaire.question_count} 题`,
      chainLabel: questionnaire.unlock_required ? "70 题链路" : "辅助参考",
      summary: copy.summary,
      helper: copy.helper,
      latestResultLabel: latestSubmission
        ? `最近结果：${RISK_LABELS[latestSubmission.risk_level] || "已保存"}`
        : "",
      resultChipClass: latestSubmission
        ? buildRiskChipClass(latestSubmission.risk_level)
        : "",
    };
  });
}

function buildModules(student, progress) {
  const treeholeDisabled = student.consent_status !== "granted";
  const missingNames = buildMissingRequiredNames(progress);
  const reportUnlocked = progress.full_profile_unlocked;

  return [
    {
      key: "report",
      title: "我的报告",
      meta: reportUnlocked
        ? "已解锁"
        : `${progress.completed_required_questions} / ${progress.total_required_questions}`,
      metaTone: reportUnlocked ? "success" : "warning",
      summary: reportUnlocked
        ? "四份必做问卷均已完成。完整综合画像报告已经达到查看条件。"
        : "完整报告仍处于锁定状态。继续完成剩余必做问卷后，可查看综合画像与调节建议。",
      hint:
        missingNames.length > 0
          ? `还需完成：${missingNames.join("、")}，也可先查看已完成量表结果`
          : "可进入报告页查看当前摘要与完整画像",
      disabled: false,
    },
    {
      key: "treehole",
      title: "树洞",
      meta: treeholeDisabled ? "暂不可用" : "可进入",
      metaTone: treeholeDisabled ? "disabled" : "default",
      summary: treeholeDisabled
        ? "你当前拒绝了危机干预授权，因此树洞入口会保持禁用。"
        : "授权已完成，后续可继续接入匿名表达、广场浏览与预设互动。",
      hint: treeholeDisabled
        ? "拒绝授权不会影响测评与报告功能"
        : "将在第 8 阶段接入树洞流程",
      disabled: treeholeDisabled,
    },
    {
      key: "help",
      title: "帮助资源",
      meta: "静态资源",
      metaTone: "default",
      summary: "求助电话、呼吸调节建议与校内心理中心信息会放在帮助页统一展示。",
      hint: "将在后续步骤开放帮助资源页",
      disabled: false,
    },
  ];
}

Page({
  data: {
    student: null,
    questionnaires: [],
    supportModules: [],
    consentDeclined: false,
    requiredProgress: buildFallbackProgress(),
    progressTitle: buildProgressTitle(buildFallbackProgress()),
    progressSummary: buildProgressSummary(buildFallbackProgress()),
    missingRequiredNames: [],
    loadingDashboard: true,
    dashboardError: "",
  },

  onShow() {
    this.bootstrap();
  },

  bootstrap() {
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

      this.setData({
        student: session.student,
        consentDeclined: session.student.consent_status === "declined",
        requiredProgress: buildFallbackProgress(),
        progressTitle: buildProgressTitle(buildFallbackProgress()),
        progressSummary: buildProgressSummary(buildFallbackProgress()),
        missingRequiredNames: [],
        loadingDashboard: true,
        dashboardError: "",
        questionnaires: [],
        supportModules: buildModules(session.student, buildFallbackProgress()),
      });
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
        this.setData({
          questionnaires: buildQuestionnaireCards(
            questionnaireData.questionnaires || []
          ),
          supportModules: buildModules(session.student, progress),
          requiredProgress: progress,
          progressTitle: buildProgressTitle(progress),
          progressSummary: buildProgressSummary(progress),
          missingRequiredNames: buildMissingRequiredNames(progress),
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
          questionnaires: [],
          supportModules: buildModules(session.student, fallbackProgress),
          requiredProgress: fallbackProgress,
          progressTitle: buildProgressTitle(fallbackProgress),
          progressSummary: "问卷目录暂时未能同步，已保留首页主入口。你可以稍后重试。",
          missingRequiredNames: [],
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

  handleModuleTap(event) {
    const { key, disabled } = event.currentTarget.dataset;
    if (disabled) {
      wx.showToast({
        title: "当前入口受授权状态限制",
        icon: "none",
      });
      return;
    }

    if (key === "report") {
      wx.navigateTo({ url: PAGE_ROUTES.REPORT_SUMMARY });
      return;
    }

    const titles = {
      treehole: "树洞流程将在后续步骤接入",
      help: "帮助资源页将在后续步骤接入",
    };

    wx.showToast({
      title: titles[key] || "该功能将在后续步骤接入",
      icon: "none",
    });
  },
});
