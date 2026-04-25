const { PAGE_ROUTES } = require("../../../constants/config");
const {
  deleteTreeholePost,
  fetchTreeholeFeed,
} = require("../../../services/treehole");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../../utils/session");
const {
  loadCachedTreeholePost,
  normalizeTreeholePost,
  removeCachedTreeholePost,
} = require("../../../utils/treehole");

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

function buildHeroCopy(post) {
  if (!post) {
    return {
      title: "帖子详情",
      summary: "这里会展示帖子的完整内容、发布时间与当前支持反馈。",
      tone: "brand",
    };
  }

  if (post.isMine) {
    return {
      title: "我的帖子详情",
      summary:
        "你可以在这里查看这条内容的公开状态与支持反馈，并在需要时执行删除。",
      tone: "brand",
    };
  }

  return {
    title: "帖子详情",
    summary: "这里展示帖子的完整内容与支持反馈。当前阶段不开放评论和私信。",
    tone: "warm",
  };
}

Page({
  data: {
    student: null,
    postId: 0,
    post: null,
    loading: true,
    loadError: "",
    deleting: false,
    showDeleteConfirm: false,
    heroTitle: "帖子详情",
    heroSummary: "这里会展示帖子的完整内容、发布时间与当前支持反馈。",
    heroTone: "brand",
  },

  onLoad(options) {
    const postId = Number(options.postId || 0);
    this.setData({
      postId,
    });
    this.bootstrap();
  },

  onPullDownRefresh() {
    this.bootstrap({ forceRemote: true });
  },

  bootstrap(options = {}) {
    const session = ensureAuthenticatedSession(this);
    if (!session) {
      wx.stopPullDownRefresh();
      return;
    }

    this.setData({
      loading: true,
      loadError: "",
    });
    this.loadDetail(session, options);
  },

  async loadDetail(session, options = {}) {
    try {
      const forceRemote = options.forceRemote === true;
      let post = !forceRemote
        ? loadCachedTreeholePost(this.data.postId)
        : null;

      if (!post && this.data.postId) {
        const feedResponse = await fetchTreeholeFeed({
          accessToken: session.accessToken,
          limit: 50,
        });
        const matchedPost = (feedResponse.posts || []).find(
          (item) => Number(item.post_id) === this.data.postId
        );
        if (matchedPost) {
          post = normalizeTreeholePost(matchedPost);
        }
      }

      const heroCopy = buildHeroCopy(post);
      this.setData({
        post,
        loading: false,
        loadError: "",
        heroTitle: heroCopy.title,
        heroSummary: heroCopy.summary,
        heroTone: heroCopy.tone,
      });
    } catch (error) {
      if (error && error.statusCode === 401) {
        clearStudentSession();
        wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
        return;
      }

      this.setData({
        loading: false,
        loadError: error.message || "帖子详情加载失败，请稍后重试。",
      });
    } finally {
      wx.stopPullDownRefresh();
    }
  },

  handleRetryLoad() {
    this.bootstrap({ forceRemote: true });
  },

  handleDeleteTap() {
    if (!this.data.post || !this.data.post.isMine || this.data.deleting) {
      return;
    }

    this.setData({
      showDeleteConfirm: true,
    });
  },

  handleDeleteCancel() {
    this.setData({
      showDeleteConfirm: false,
    });
  },

  async handleDeleteConfirm() {
    const currentSession = ensureAuthenticatedSession();
    if (!currentSession || !this.data.post || !this.data.post.isMine) {
      return;
    }

    this.setData({
      showDeleteConfirm: false,
      deleting: true,
    });

    try {
      await deleteTreeholePost({
        accessToken: currentSession.accessToken,
        postId: this.data.post.postId,
      });
      removeCachedTreeholePost(this.data.post.postId);
      wx.showToast({
        title: "帖子已从广场移除",
        icon: "success",
      });
      setTimeout(() => {
        this.handleBackToFeed();
      }, 480);
    } catch (error) {
      if (error && error.statusCode === 401) {
        clearStudentSession();
        wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
        return;
      }

      this.setData({
        deleting: false,
        loadError: error.message || "删除失败，请稍后重试。",
      });
    }
  },

  handleBackToFeed() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.reLaunch({ url: PAGE_ROUTES.TREEHOLE_FEED });
  },
});
