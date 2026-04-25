const { HOTLINE_PHONE, PAGE_ROUTES } = require("../constants/config");
const {
  getQuestionnairePageConfig,
  getQuestionnaireRouteByCode,
} = require("../constants/questionnaires");
const {
  fetchQuestionnaireDetail,
  fetchRequiredProgress,
  submitQuestionnaire,
} = require("../services/questionnaires");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("./session");

const RISK_LABELS = {
  low: "低风险",
  watch: "需关注",
  high: "高风险",
};
const RISK_TONES = {
  low: "brand",
  watch: "warm",
  high: "danger",
};
const BADGE_TONES = {
  low: "low",
  watch: "watch",
  high: "high",
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

function buildQuestionCards(questionnaire, answers, missingQuestionCodes) {
  if (!questionnaire || !Array.isArray(questionnaire.questions)) {
    return [];
  }

  const missingSet = new Set(missingQuestionCodes || []);
  return questionnaire.questions.map((question) => ({
    question_code: question.question_code,
    question_order: question.question_order,
    question_text: question.question_text,
    question_type: question.question_type,
    anchor_id: `question-${question.question_code.toLowerCase()}`,
    description: missingSet.has(question.question_code)
      ? "这一题还没有作答，请先补全后再提交。"
      : "",
    missing: missingSet.has(question.question_code),
    options: (question.options || []).map((option) => ({
      value: option.value,
      label: option.label,
      selected: answers[question.question_code] === option.value,
    })),
  }));
}

function buildProgressCard(pageConfig, progress) {
  const safeProgress = progress || buildFallbackProgress();
  if (!pageConfig.unlockRequired) {
    return {
      eyebrow: "辅助说明",
      title: "这份问卷不影响完整报告解锁",
      summary: safeProgress.total_required_questions
        ? `当前必做进度为 ${safeProgress.completed_required_questions} / ${safeProgress.total_required_questions} 题。UPI 仅作为辅助参考信号。`
        : "UPI 仅作为辅助参考信号，不影响 70 题完整报告解锁。",
      showProgressBar: Boolean(safeProgress.total_required_questions),
      current: safeProgress.completed_required_questions,
      total: safeProgress.total_required_questions,
      helper: pageConfig.optionalHint,
    };
  }

  return {
    eyebrow: "固定进度",
    title: `必做进度 ${safeProgress.completed_required_questions} / ${safeProgress.total_required_questions}`,
    summary: safeProgress.full_profile_unlocked
      ? "四份必做问卷均已完成。返回首页后即可查看完整报告解锁状态。"
      : "这份问卷属于固定 70 题链路的一部分。提交后，首页和后续报告会以最新结果刷新进度。",
    showProgressBar: Boolean(safeProgress.total_required_questions),
    current: safeProgress.completed_required_questions,
    total: safeProgress.total_required_questions,
    helper: pageConfig.scaleLabel,
  };
}

function buildLatestSubmissionHint(questionnaire, pageConfig) {
  if (!questionnaire || !questionnaire.latest_submission) {
    return "";
  }

  const latestSubmission = questionnaire.latest_submission;
  const riskLabel = RISK_LABELS[latestSubmission.risk_level] || "已保存";
  const scoreText =
    latestSubmission.standardized_score !== null &&
    latestSubmission.standardized_score !== undefined
      ? `标准分 ${latestSubmission.standardized_score}`
      : `总分 ${latestSubmission.raw_score}`;
  return `${pageConfig.latestHint} 最近一次结果为 ${riskLabel}（${scoreText}）。`;
}

function buildRiskFollowUpItems(riskLevel, pageConfig) {
  if (riskLevel === "high") {
    return [
      "请优先联系可信赖的人，不要独自承受当前压力。",
      "如果当下已经感到急迫或失控，请尽快联系校内心理中心或求助热线。",
      pageConfig.disclaimer,
    ];
  }

  if (riskLevel === "watch") {
    return [
      "建议继续完成剩余问卷或回到首页查看整体进度，让结果更完整。",
      "这几天尽量保持基本作息，并主动与可信赖的人保持联系。",
      pageConfig.disclaimer,
    ];
  }

  return [
    "这次结果可以作为当前状态的一个温和参考，后续仍可根据近况变化重新作答。",
    "如果你仍对最近的体验感到在意，可以继续完成后续问卷获取更完整的画像。",
    pageConfig.disclaimer,
  ];
}

function buildPrimaryAction(pageConfig, riskLevel) {
  if (riskLevel === "high") {
    return {
      label: pageConfig.homeLabel || "返回首页",
      route: PAGE_ROUTES.HOME,
      mode: "reLaunch",
      tone: "danger",
    };
  }

  if (pageConfig.nextCode) {
    return {
      label: pageConfig.nextLabel,
      route: getQuestionnaireRouteByCode(pageConfig.nextCode),
      mode: "redirectTo",
      tone: "primary",
    };
  }

  return {
    label: pageConfig.homeLabel || "返回首页",
    route: PAGE_ROUTES.HOME,
    mode: "reLaunch",
    tone: "primary",
  };
}

function buildResultView(pageConfig, submissionResult, progress) {
  const riskLevel = submissionResult.risk_level;
  const resultCopy =
    (pageConfig.resultCopy && pageConfig.resultCopy[riskLevel]) || {};
  const safeProgress = progress || buildFallbackProgress();
  let primaryAction = buildPrimaryAction(pageConfig, riskLevel);
  if (
    riskLevel !== "high" &&
    safeProgress.full_profile_unlocked &&
    !pageConfig.nextCode
  ) {
    primaryAction = {
      label: "查看完整报告",
      route: PAGE_ROUTES.REPORT_FULL,
      mode: "redirectTo",
      tone: "primary",
    };
  }

  return {
    questionnaireCode: submissionResult.questionnaire_code,
    badgeLabel: RISK_LABELS[riskLevel] || "结果已保存",
    badgeTone: BADGE_TONES[riskLevel] || "low",
    heroTone: RISK_TONES[riskLevel] || "brand",
    title: resultCopy.title || `${pageConfig.name}结果已更新`,
    summary: resultCopy.summary || "本次作答已成功保存。",
    scoreLabel: pageConfig.scoreLabel,
    scoreValue:
      submissionResult.standardized_score !== null &&
      submissionResult.standardized_score !== undefined
        ? submissionResult.standardized_score
        : submissionResult.raw_score,
    scoreHelper:
      submissionResult.standardized_score !== null &&
      submissionResult.standardized_score !== undefined
        ? `原始分 ${submissionResult.raw_score}`
        : `已按 ${pageConfig.scaleLabel} 规则完成计算`,
    showSafetyBanner: riskLevel === "high",
    safetyTitle: "请优先照顾当下安全与支持",
    safetyMessage:
      "如果你现在已经感到明显难以承受，请尽快联系可信赖的人、校内心理中心，或直接拨打热线寻求帮助。",
    followUpItems: buildRiskFollowUpItems(riskLevel, pageConfig),
    primaryAction,
    progressCard: buildProgressCard(pageConfig, safeProgress),
    fullProfileUnlocked: safeProgress.full_profile_unlocked,
    submittedSummary: safeProgress.full_profile_unlocked
      ? "这次提交已经纳入完整报告链路。返回首页后可继续查看最新解锁状态。"
      : `当前固定进度为 ${safeProgress.completed_required_questions} / ${safeProgress.total_required_questions} 题。`,
  };
}

function extractMissingQuestionCodes(errors) {
  if (!Array.isArray(errors)) {
    return [];
  }

  return errors
    .map((error) => {
      if (!error || typeof error.field !== "string") {
        return "";
      }
      if (!error.field.startsWith("answers.")) {
        return "";
      }
      return error.field.slice("answers.".length).toUpperCase();
    })
    .filter(Boolean);
}

function scrollToQuestion(anchorId) {
  if (!anchorId) {
    return;
  }

  wx.pageScrollTo({
    selector: `#${anchorId}`,
    duration: 240,
  });
}

function buildSubmitPayload(questionCards, answers) {
  return questionCards.map((question) => ({
    question_code: question.question_code,
    selected_option: answers[question.question_code],
  }));
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

function createQuestionnairePage(questionnaireCode) {
  const pageConfig = getQuestionnairePageConfig(questionnaireCode);
  if (!pageConfig) {
    throw new Error(`unknown questionnaire code '${questionnaireCode}'`);
  }

  return {
    data: {
      pageConfig,
      hotlinePhone: HOTLINE_PHONE,
      student: null,
      questionnaire: null,
      questionCards: [],
      answers: {},
      missingQuestionCodes: [],
      progress: buildFallbackProgress(),
      progressCard: buildProgressCard(pageConfig, buildFallbackProgress()),
      latestSubmissionHint: "",
      loading: true,
      loadError: "",
      submitting: false,
      submitError: "",
      resultView: null,
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
        submitError: "",
        resultView: null,
        answers: {},
        missingQuestionCodes: [],
      });

      Promise.all([
        fetchQuestionnaireDetail({
          accessToken: session.accessToken,
          code: pageConfig.code,
        }),
        fetchRequiredProgress({ accessToken: session.accessToken }).catch(() => ({
          progress: buildFallbackProgress(),
        })),
      ])
        .then(([detailResponse, progressResponse]) => {
          const questionnaire = detailResponse.questionnaire;
          const progress =
            progressResponse && progressResponse.progress
              ? progressResponse.progress
              : buildFallbackProgress();

          this.setData({
            questionnaire,
            progress,
            progressCard: buildProgressCard(pageConfig, progress),
            latestSubmissionHint: buildLatestSubmissionHint(
              questionnaire,
              pageConfig
            ),
            questionCards: buildQuestionCards(questionnaire, {}, []),
            answers: {},
            missingQuestionCodes: [],
            loading: false,
            loadError: "",
            submitError: "",
          });
        })
        .catch((error) => {
          if (error && error.statusCode === 401) {
            clearStudentSession();
            wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
            return;
          }

          this.setData({
            loading: false,
            loadError:
              (error && error.message) || "问卷加载失败，请稍后重试。",
          });
        })
        .finally(() => {
          wx.stopPullDownRefresh();
        });
    },

    updateQuestionCards(answers, missingQuestionCodes) {
      const questionnaire = this.data.questionnaire;
      this.setData({
        questionCards: buildQuestionCards(
          questionnaire,
          answers,
          missingQuestionCodes
        ),
        answers,
        missingQuestionCodes,
      });
    },

    handleRetryLoad() {
      this.bootstrap();
    },

    handleSelectOption(event) {
      const { questionCode, value } = event.currentTarget.dataset;
      const normalizedCode = String(questionCode).toUpperCase();
      const answers = {
        ...this.data.answers,
        [normalizedCode]: value,
      };
      const missingQuestionCodes = this.data.missingQuestionCodes.filter(
        (item) => item !== normalizedCode
      );
      this.updateQuestionCards(answers, missingQuestionCodes);
      this.setData({
        submitError: "",
      });
    },

    validateAnswers() {
      const questionCards = this.data.questionCards || [];
      const answers = this.data.answers || {};
      const missingQuestionCodes = questionCards
        .filter((question) => !answers[question.question_code])
        .map((question) => question.question_code);

      if (!missingQuestionCodes.length) {
        return true;
      }

      this.updateQuestionCards(answers, missingQuestionCodes);
      this.setData({
        submitError: "还有未作答题目，请先补全后再提交。",
      });
      wx.showToast({
        title: "请先完成所有题目",
        icon: "none",
      });
      const firstMissing = questionCards.find(
        (question) => question.question_code === missingQuestionCodes[0]
      );
      scrollToQuestion(firstMissing && firstMissing.anchor_id);
      return false;
    },

    handleSubmit() {
      const session = ensureAuthenticatedSession(this);
      if (!session || this.data.submitting) {
        return;
      }

      if (!this.validateAnswers()) {
        return;
      }

      const answersPayload = buildSubmitPayload(
        this.data.questionCards,
        this.data.answers
      );
      this.setData({
        submitting: true,
        submitError: "",
      });

      submitQuestionnaire({
        accessToken: session.accessToken,
        code: pageConfig.code,
        answers: answersPayload,
      })
        .then((submissionResult) =>
          fetchRequiredProgress({
            accessToken: session.accessToken,
          })
            .then((progressResponse) => ({
              submissionResult,
              progress: progressResponse.progress || this.data.progress,
            }))
            .catch(() => ({
              submissionResult,
              progress: this.data.progress,
            }))
        )
        .then(({ submissionResult, progress }) => {
          const resultView = buildResultView(
            pageConfig,
            submissionResult,
            progress
          );
          this.setData({
            submitting: false,
            submitError: "",
            loadError: "",
            progress,
            progressCard: buildProgressCard(pageConfig, progress),
            latestSubmissionHint: "",
            missingQuestionCodes: [],
            resultView,
          });
          wx.pageScrollTo({
            scrollTop: 0,
            duration: 240,
          });
        })
        .catch((error) => {
          if (error && error.statusCode === 401) {
            clearStudentSession();
            wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
            return;
          }

          const missingQuestionCodes =
            error && error.code === "QUESTIONNAIRE_SUBMISSION_INCOMPLETE"
              ? extractMissingQuestionCodes(error.errors)
              : [];
          if (missingQuestionCodes.length) {
            this.updateQuestionCards(this.data.answers, missingQuestionCodes);
            const firstMissing = this.data.questionCards.find(
              (question) =>
                question.question_code === missingQuestionCodes[0]
            );
            scrollToQuestion(firstMissing && firstMissing.anchor_id);
          }

          this.setData({
            submitting: false,
            submitError:
              (error && error.message) || "提交失败，请稍后重试。",
          });
        });
    },

    handleRetrySubmit() {
      this.handleSubmit();
    },

    handleRetake() {
      this.setData({
        resultView: null,
        submitError: "",
        missingQuestionCodes: [],
      });
      this.updateQuestionCards(this.data.answers || {}, []);
      wx.pageScrollTo({
        scrollTop: 0,
        duration: 240,
      });
    },

    handlePrimaryAction() {
      const resultView = this.data.resultView;
      if (!resultView || !resultView.primaryAction) {
        wx.reLaunch({ url: PAGE_ROUTES.HOME });
        return;
      }

      const action = resultView.primaryAction;
      if (action.mode === "redirectTo") {
        wx.redirectTo({ url: action.route });
        return;
      }

      wx.reLaunch({ url: action.route || PAGE_ROUTES.HOME });
    },

    handleBackHome() {
      wx.reLaunch({ url: PAGE_ROUTES.HOME });
    },
  };
}

module.exports = {
  createQuestionnairePage,
};
