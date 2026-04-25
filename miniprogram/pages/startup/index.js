const { PAGE_ROUTES } = require("../../constants/config");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../utils/session");

Page({
  data: {
    statusText: "正在检查本地会话…",
  },

  onShow() {
    this.bootstrap();
  },

  bootstrap() {
    if (this.redirecting) {
      return;
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
