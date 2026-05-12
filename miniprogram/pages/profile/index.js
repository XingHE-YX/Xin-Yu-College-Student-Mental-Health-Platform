const { PAGE_ROUTES } = require("../../constants/config");
const { getPrimaryChannelRoute } = require("../../constants/navigation");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../utils/session");

function buildRuntimeHints(features) {
  const hints = [];
  if (!features) {
    return hints;
  }
  if (features.enableDemoLogin) {
    hints.push("当前环境已开启演示登录入口。");
  }
  if (features.enableMockAi) {
    hints.push("当前环境启用了本地模拟 AI 容错。");
  }
  if (features.showSeededCases) {
    hints.push("当前环境允许展示预置演示案例。");
  }
  return hints;
}

Page({
  data: {
    student: null,
    runtimeHints: [],
  },

  onShow() {
    this.bootstrap();
  },

  bootstrap() {
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

    const runtimeFeatures =
      (getApp().globalData && getApp().globalData.runtimeFeatures) || null;
    this.setData({
      student: session.student,
      runtimeHints: buildRuntimeHints(runtimeFeatures),
    });
  },

  handleOpenHelp() {
    wx.navigateTo({ url: PAGE_ROUTES.HELP });
  },

  handleOpenReport() {
    wx.reLaunch({ url: PAGE_ROUTES.REPORT_SUMMARY });
  },

  handleChannelChange(event) {
    const { key } = event.detail || {};
    const route = getPrimaryChannelRoute(key);
    if (!route || route === PAGE_ROUTES.PROFILE) {
      return;
    }
    wx.reLaunch({ url: route });
  },

  handleLogout() {
    clearStudentSession();
    getApp().globalData.studentSession = null;
    wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
  },
});
