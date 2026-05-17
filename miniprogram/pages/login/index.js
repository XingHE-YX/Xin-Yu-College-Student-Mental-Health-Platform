const {
  PAGE_ROUTES,
  buildDefaultRuntimeFeatures,
} = require("../../constants/config");
const { loginWithDemo, loginWithWechat } = require("../../services/auth");
const { fetchRuntimeFeatures } = require("../../services/runtime");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
  saveStudentSession,
} = require("../../utils/session");
const { relaunchOrSwitchTab } = require("../../utils/navigation");

function normalizePhoneInput(rawValue) {
  return String(rawValue || "").replace(/[^\d+]/g, "");
}

function buildDemoModeHint(features) {
  const hints = [];
  if (features.enableMockAi) {
    hints.push("已启用本地模拟 AI 分析");
  }
  if (features.showSeededCases) {
    hints.push("后台将显示预置演示案例");
  }
  if (!hints.length) {
    return "";
  }
  return `当前演示容错模式：${hints.join("；")}。`;
}

Page({
  data: {
    loginCodeReady: false,
    loginCode: "",
    wechatLoading: false,
    loginLoading: false,
    demoLoading: false,
    showDemoEntry: false,
    runtimeFeatures: buildDefaultRuntimeFeatures(),
    demoModeHint: "",
    errorMessage: "",
    statusMessage: "",
    phoneRefused: false,
    form: {
      phoneNumber: "",
      collegeName: "",
      className: "",
    },
  },

  onLoad() {
    this.loadRuntimeFeatures();
  },

  onShow() {
    try {
      const session = loadStudentSession();
      if (hasValidStudentSession(session)) {
        getApp().globalData.studentSession = session;
        const nextRoute =
          session.student.consent_status === "missing"
            ? PAGE_ROUTES.CONSENT
            : PAGE_ROUTES.HOME;
        relaunchOrSwitchTab(nextRoute);
      }
    } catch (error) {
      clearStudentSession();
    }
  },

  handleInputChange(event) {
    const { field } = event.currentTarget.dataset;
    const value =
      field === "phoneNumber"
        ? normalizePhoneInput(event.detail.value)
        : event.detail.value;

    this.setData({
      [`form.${field}`]: value,
      errorMessage: "",
    });
  },

  handleWechatLogin() {
    if (this.data.wechatLoading) {
      return;
    }

    this.setData({
      wechatLoading: true,
      errorMessage: "",
      statusMessage: "",
      phoneRefused: false,
    });

    wx.login({
      success: (result) => {
        if (!result.code) {
          this.setData({
            errorMessage: "微信登录未返回有效 code，请稍后重试。",
            wechatLoading: false,
          });
          return;
        }

        this.setData({
          loginCodeReady: true,
          loginCode: result.code,
          wechatLoading: false,
          statusMessage: "微信登录状态已获取，请继续完成手机号授权。",
        });
      },
      fail: () => {
        this.setData({
          wechatLoading: false,
          errorMessage: "微信登录失败，请点击按钮重新尝试。",
        });
      },
    });
  },

  handlePhoneRefuse() {
    this.setData({
      phoneRefused: true,
      errorMessage:
        "拒绝手机号授权后无法创建学生会话。你可以继续留在本页并重新尝试授权。",
    });
  },

  async handleWechatSubmit() {
    if (this.data.loginLoading) {
      return;
    }

    if (!this.data.loginCode) {
      this.setData({
        errorMessage: "请先完成微信登录，再继续手机号授权。",
      });
      return;
    }

    if (!/^(\+?\d{6,20}|1\d{10})$/.test(this.data.form.phoneNumber)) {
      this.setData({
        errorMessage: "请输入有效手机号，用于创建校园学生会话。",
      });
      return;
    }

    this.setData({
      loginLoading: true,
      errorMessage: "",
      statusMessage: "正在创建学生会话…",
      phoneRefused: false,
    });

    try {
      const sessionData = await loginWithWechat({
        loginCode: this.data.loginCode,
        phoneNumber: this.data.form.phoneNumber,
        collegeName: this.data.form.collegeName.trim(),
        className: this.data.form.className.trim(),
      });
      const savedSession = saveStudentSession(sessionData);
      getApp().globalData.studentSession = savedSession;

      relaunchOrSwitchTab(
        savedSession.student.consent_status === "missing"
          ? PAGE_ROUTES.CONSENT
          : PAGE_ROUTES.HOME
      );
    } catch (error) {
      this.setData({
        loginLoading: false,
        statusMessage: "",
        errorMessage:
          error.message || "登录失败，请确认本地后端已启动后重试。",
      });
    }
  },

  async handleDemoLogin() {
    if (this.data.demoLoading) {
      return;
    }

    this.setData({
      demoLoading: true,
      errorMessage: "",
      statusMessage: "正在进入演示账号…",
    });

    try {
      const sessionData = await loginWithDemo();
      const savedSession = saveStudentSession(sessionData);
      getApp().globalData.studentSession = savedSession;
      relaunchOrSwitchTab(
        savedSession.student.consent_status === "missing"
          ? PAGE_ROUTES.CONSENT
          : PAGE_ROUTES.HOME
      );
    } catch (error) {
      this.setData({
        demoLoading: false,
        statusMessage: "",
        showDemoEntry:
          error.code === "DEMO_LOGIN_DISABLED" ? false : this.data.showDemoEntry,
        errorMessage:
          error.message || "演示登录失败，请稍后重试或改用微信登录。",
      });
    }
  },

  async loadRuntimeFeatures() {
    const app = getApp();
    const cachedFeatures =
      app.globalData.runtimeFeatures || buildDefaultRuntimeFeatures();
    this.applyRuntimeFeatures(cachedFeatures);

    try {
      const runtimeFeatures =
        typeof app.syncRuntimeFeatures === "function"
          ? await app.syncRuntimeFeatures()
          : await fetchRuntimeFeatures();
      this.applyRuntimeFeatures(runtimeFeatures);
    } catch (error) {
      this.applyRuntimeFeatures(buildDefaultRuntimeFeatures());
    }
  },

  applyRuntimeFeatures(runtimeFeatures) {
    this.setData({
      runtimeFeatures,
      showDemoEntry: runtimeFeatures.enableDemoLogin,
      demoModeHint: buildDemoModeHint(runtimeFeatures),
    });
  },
});
