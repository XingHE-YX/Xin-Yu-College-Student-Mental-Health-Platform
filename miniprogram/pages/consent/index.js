const { CONSENT_VERSION, HOTLINE_PHONE, PAGE_ROUTES } = require("../../constants/config");
const { submitConsent } = require("../../services/auth");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
  saveStudentSession,
} = require("../../utils/session");

Page({
  data: {
    student: null,
    submitting: false,
    errorMessage: "",
    statusMessage: "",
    showDeclineConfirm: false,
    hotlinePhone: HOTLINE_PHONE,
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
      if (session.student.consent_status !== "missing") {
        wx.reLaunch({ url: PAGE_ROUTES.HOME });
        return;
      }

      this.setData({
        student: session.student,
        errorMessage: "",
      });
    } catch (error) {
      clearStudentSession();
      wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
    }
  },

  handleAgree() {
    this.submitConsentDecision(true);
  },

  handleDeclineTap() {
    this.setData({
      showDeclineConfirm: true,
    });
  },

  handleDeclineCancel() {
    this.setData({
      showDeclineConfirm: false,
    });
  },

  handleDeclineConfirm() {
    this.setData({
      showDeclineConfirm: false,
    });
    this.submitConsentDecision(false);
  },

  async submitConsentDecision(granted) {
    if (this.data.submitting) {
      return;
    }

    const currentSession = loadStudentSession();
    if (!hasValidStudentSession(currentSession)) {
      clearStudentSession();
      wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
      return;
    }

    this.setData({
      submitting: true,
      errorMessage: "",
      statusMessage: granted ? "正在保存授权结果…" : "正在保存拒绝记录…",
    });

    try {
      let nextSessionPayload = await submitConsent({
        accessToken: currentSession.accessToken,
        consentType: "privacy_policy",
        consentVersion: CONSENT_VERSION,
        granted: true,
      });
      let savedSession = saveStudentSession(nextSessionPayload);
      getApp().globalData.studentSession = savedSession;

      nextSessionPayload = await submitConsent({
        accessToken: savedSession.accessToken,
        consentType: "crisis_intervention_authorization",
        consentVersion: CONSENT_VERSION,
        granted,
      });
      savedSession = saveStudentSession(nextSessionPayload);
      getApp().globalData.studentSession = savedSession;

      wx.reLaunch({ url: PAGE_ROUTES.HOME });
    } catch (error) {
      this.setData({
        submitting: false,
        statusMessage: "",
        errorMessage:
          error.message || "授权结果保存失败，请留在当前页重试。",
      });
    }
  },
});
