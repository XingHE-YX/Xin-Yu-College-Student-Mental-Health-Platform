const { HOTLINE_PHONE, PAGE_ROUTES } = require("../../../constants/config");
const { createTreeholePost } = require("../../../services/treehole");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../../utils/session");
const {
  buildCreatedTreeholePost,
  buildTreeholeDetailRoute,
  cacheTreeholePost,
} = require("../../../utils/treehole");
const { switchToPrimaryTab } = require("../../../utils/navigation");
const { markChannelDirty } = require("../../../utils/channel-sync");

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
      pageMode:
        session.student.consent_status === "granted" ? "editor" : "disabled",
    });
  }
  return session;
}

Page({
  data: {
    student: null,
    hotlinePhone: HOTLINE_PHONE,
    pageMode: "editor",
    heroTitle: "写下一条匿名心情",
    heroSummary:
      "内容会先经过匿名与脱敏处理，再按风险进入公开发布、温和提醒或安全拦截分流。",
    heroTone: "brand",
    content: "",
    contentLength: 0,
    contentError: "",
    submitError: "",
    submitting: false,
    createdPost: null,
    successMessage: "",
    successTitle: "",
    successSummary: "",
    successBadgeLabel: "",
  },

  onLoad() {
    this.bootstrap();
  },

  bootstrap() {
    const session = ensureAuthenticatedSession(this);
    if (!session) {
      return;
    }

    if (session.student.consent_status !== "granted") {
      this.setData({
        heroTitle: "当前还不能发布树洞",
        heroSummary:
          "树洞功能需要危机干预授权为 granted。你仍可以保留问卷和报告链路。",
        heroTone: "warm",
      });
      return;
    }

    this.setData({
      heroTitle: "写下一条匿名心情",
      heroSummary:
        "内容会先经过匿名与脱敏处理，再按风险进入公开发布、温和提醒或安全拦截分流。",
      heroTone: "brand",
    });
  },

  handleContentInput(event) {
    const value = String(event.detail.value || "");
    this.setData({
      content: value,
      contentLength: value.length,
      contentError: "",
      submitError: "",
    });
  },

  async handleSubmit() {
    if (this.data.submitting || this.data.pageMode !== "editor") {
      return;
    }

    const currentSession = ensureAuthenticatedSession();
    if (!currentSession) {
      return;
    }

    const normalizedContent = this.data.content.replace(/\r\n/g, "\n").trim();
    if (!normalizedContent) {
      this.setData({
        contentError: "内容不能为空。请先写下你想表达的心情，再继续发布。",
      });
      wx.showToast({
        title: "请先输入内容",
        icon: "none",
      });
      return;
    }

    this.setData({
      submitting: true,
      contentError: "",
      submitError: "",
    });

    try {
      const result = await createTreeholePost({
        accessToken: currentSession.accessToken,
        content: normalizedContent,
      });
      const createdPost = buildCreatedTreeholePost(result);
      cacheTreeholePost(createdPost);
      markChannelDirty("treehole");

      if (
        result.publish_status === "blocked_high_risk" ||
        result.risk_level === "high"
      ) {
        this.setData({
          hotlinePhone: result.hotline || HOTLINE_PHONE,
          pageMode: "intercept",
          heroTitle: "这条内容暂不适合公开发布",
          heroSummary:
            "系统识别到当前内容需要优先进入安全支持流程，因此不会把它直接展示到广场。",
          heroTone: "warm",
          createdPost,
          submitting: false,
        });
        return;
      }

      const isWatch = result.risk_level === "watch";
      this.setData({
        pageMode: "success",
        heroTitle: isWatch ? "内容已发布，并建议继续留意状态" : "内容已成功发布到匿名广场",
        heroSummary: isWatch
          ? "这条树洞已经公开，同时系统建议你继续留意近期状态变化。"
          : "这条树洞已经进入公开广场，其他同学只能看到匿名昵称、头像和脱敏正文。",
        heroTone: isWatch ? "warm" : "brand",
        createdPost,
        content: "",
        contentLength: 0,
        successMessage: isWatch
          ? "发布成功。若你近期持续感到吃力，也可以继续查看报告或完成后续问卷。"
          : "发布成功。现在你可以回到广场，或直接进入自己的帖子详情页。",
        successTitle: isWatch ? "发布成功，并附带温和提醒" : "发布成功",
        successSummary: isWatch
          ? "系统已保留这条匿名内容，并建议你继续关注自己的节奏、睡眠与支持网络。"
          : "这条内容已经以匿名身份进入广场。公开版正文只保留脱敏后的文本，不展示真实身份。",
        successBadgeLabel: isWatch ? "需关注" : "低风险",
        submitting: false,
      });
    } catch (error) {
      if (error && error.statusCode === 401) {
        clearStudentSession();
        wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
        return;
      }

      if (error && error.code === "TREEHOLE_CONTENT_EMPTY") {
        this.setData({
          contentError: "内容不能为空。请先写下你想表达的心情，再继续发布。",
          submitting: false,
        });
        return;
      }

      if (error && error.code === "TREEHOLE_CONSENT_REQUIRED") {
        this.setData({
          pageMode: "disabled",
          heroTitle: "当前还不能发布树洞",
          heroSummary:
            "树洞功能需要危机干预授权为 granted。你仍可以保留问卷和报告链路。",
          heroTone: "warm",
          submitting: false,
        });
        return;
      }

      this.setData({
        submitError: error.message || "树洞发布失败，请稍后重试。",
        submitting: false,
      });
    }
  },

  handleViewMyPost() {
    if (!this.data.createdPost || !this.data.createdPost.postId) {
      return;
    }

    cacheTreeholePost(this.data.createdPost);
    wx.redirectTo({
      url: buildTreeholeDetailRoute(this.data.createdPost.postId),
    });
  },

  handleBackToFeed() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    switchToPrimaryTab(PAGE_ROUTES.TREEHOLE_FEED);
  },

  handleCallHotline() {
    wx.makePhoneCall({
      phoneNumber: this.data.hotlinePhone,
      fail: () => {
        wx.showToast({
          title: "拨号失败，请手动联系热线",
          icon: "none",
        });
      },
    });
  },

  handleBackHome() {
    switchToPrimaryTab(PAGE_ROUTES.HOME);
  },
});
