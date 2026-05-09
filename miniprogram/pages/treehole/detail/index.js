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
  buildDeletedTreeholePost,
  cacheTreeholePost,
  loadCachedTreeholePost,
  normalizeTreeholePost,
  setRecentTreeholeDeleteNotice,
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

function buildDeleteCopy(student) {
  const isDemo = Boolean(student && student.is_demo);
  return {
    deletedHeroSummary: isDemo
      ? "这条内容已经按软删除规则从学生端广场和详情链路中移除，后台仍会保留记录。"
      : "这条内容已经从学生端广场和详情页中移除，你现在不会再在学生端看到它。",
    deletedStatusMessage: isDemo
      ? "这条帖子已从学生端移除。后台仍会保留记录，以满足审计与复核需要。"
      : "这条帖子已从学生端移除。",
    deletedCardBody: isDemo
      ? "删除采用软删除方式：广场和学生端详情不再公开显示这条内容，但后台仍会保留记录，用于后续审计与复核。"
      : "删除完成后，这条内容不会再出现在学生端广场和你的详情页中。当前阶段不支持恢复，请确认后再执行删除。",
    deleteInfoBody: isDemo
      ? "删除采用软删除方式：学生端将不再显示这条帖子，但后台仍会保留记录以满足审计与复核需要。"
      : "删除后，这条帖子会从学生端广场和你的详情页中移除。当前阶段不支持恢复，请确认后再执行删除。",
    deleteConfirmMessage: isDemo
      ? "删除后，这条内容会从学生端广场中消失，但后台仍会保留记录。这个操作无法在当前阶段恢复。"
      : "删除后，这条内容会从学生端广场和你的详情页中移除。这个操作当前无法恢复。",
    deletedChipLabel: isDemo ? "后台仍保留记录" : "学生端已移除",
  };
}

function buildHeroCopy(post, student) {
  if (!post) {
    return {
      title: "帖子详情",
      summary: "这里会展示帖子的完整内容、发布时间与当前支持反馈。",
      tone: "brand",
    };
  }

  if (post.publishStatus === "deleted_by_user") {
    const deleteCopy = buildDeleteCopy(student);
    return {
      title: "帖子已从学生端移除",
      summary: deleteCopy.deletedHeroSummary,
      tone: "warm",
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
    statusMessage: "",
    deleting: false,
    showDeleteConfirm: false,
    heroTitle: "帖子详情",
    heroSummary: "这里会展示帖子的完整内容、发布时间与当前支持反馈。",
    heroTone: "brand",
    deleteCopy: buildDeleteCopy(null),
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
      statusMessage: "",
    });
    this.loadDetail(session, options);
  },

  async loadDetail(session, options = {}) {
    try {
      const forceRemote = options.forceRemote === true;
      const cachedPost = this.data.postId
        ? loadCachedTreeholePost(this.data.postId)
        : null;
      let post = !forceRemote ? cachedPost : null;

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
        } else if (
          cachedPost &&
          cachedPost.publishStatus === "deleted_by_user"
        ) {
          post = cachedPost;
        }
      }

      const heroCopy = buildHeroCopy(post, session.student);
      const deleteCopy = buildDeleteCopy(session.student);
      this.setData({
        post,
        loading: false,
        loadError: "",
        statusMessage:
          post && post.publishStatus === "deleted_by_user"
            ? deleteCopy.deletedStatusMessage
            : "",
        heroTitle: heroCopy.title,
        heroSummary: heroCopy.summary,
        heroTone: heroCopy.tone,
        deleteCopy,
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
      const deleteResult = await deleteTreeholePost({
        accessToken: currentSession.accessToken,
        postId: this.data.post.postId,
      });
      const deletedPost = buildDeletedTreeholePost(this.data.post, {
        deletedAt: deleteResult.deleted_at,
      });
      const deleteCopy = buildDeleteCopy(currentSession.student);
      const heroCopy = buildHeroCopy(deletedPost, currentSession.student);
      cacheTreeholePost(deletedPost);
      setRecentTreeholeDeleteNotice(deletedPost, {
        isDemo: currentSession.student.is_demo === true,
      });
      this.setData({
        post: deletedPost,
        deleting: false,
        loadError: "",
        statusMessage: deleteCopy.deletedStatusMessage,
        heroTitle: heroCopy.title,
        heroSummary: heroCopy.summary,
        heroTone: heroCopy.tone,
        deleteCopy,
      });
      wx.showToast({
        title: "已从学生端移除",
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
