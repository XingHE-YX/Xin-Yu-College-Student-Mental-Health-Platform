const { PAGE_ROUTES } = require("../../constants/config");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../utils/session");

Page({
  data: {
    statusText: "正在检查本地会话与演示模式…",
  },

  onShow() {
    this.bootstrap();
  },

  bootstrap() {
    if (this.redirecting) {
      return;
    }

    const app = getApp();
    if (typeof app.syncRuntimeFeatures === "function") {
      app.syncRuntimeFeatures();
    }

    try {
      const session = loadStudentSession();
      if (hasValidStudentSession(session)) {
        getApp().globalData.studentSession = session;
        if (session.student.consent_status === "missing") {
          this.redirectTo(PAGE_ROUTES.CONSENT);
          return;
        }
        this.redirectTo(PAGE_ROUTES.HOME);
        return;
      }
    } catch (error) {
      this.setData({
        statusText: "本地会话读取失败，正在重置登录状态…",
      });
    }

    clearStudentSession();
    getApp().globalData.studentSession = null;
    this.redirectTo(PAGE_ROUTES.LOGIN);
  },

  redirectTo(url) {
    this.redirecting = true;
    wx.reLaunch({ url });
  },
});
