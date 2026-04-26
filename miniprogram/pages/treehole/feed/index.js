const { PAGE_ROUTES } = require("../../../constants/config");
const {
  fetchTreeholeFeed,
  submitTreeholeReaction,
} = require("../../../services/treehole");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../../utils/session");
const {
  applyOptimisticTreeholeReaction,
  buildTreeholeDetailRoute,
  cacheTreeholePost,
  consumeRecentTreeholeDeleteNotice,
  hasReactedToTreehole,
  mergeTreeholeReactionResult,
  normalizeTreeholePost,
} = require("../../../utils/treehole");

function buildFeedMetrics(posts = []) {
  return {
    publicCount: posts.length,
    myCount: posts.filter((post) => post.isMine).length,
    supportCount: posts.reduce(
      (sum, post) => sum + Number(post.totalReactionCount || 0),
      0
    ),
  };
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
      feedDisabled: session.student.consent_status !== "granted",
    });
  }
  return session;
}

Page({
  data: {
    student: null,
    feedDisabled: false,
    loading: true,
    loadError: "",
    deleteNotice: "",
    posts: [],
    metrics: buildFeedMetrics(),
  },

  onShow() {
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

    const deleteNotice = consumeRecentTreeholeDeleteNotice();

    if (session.student.consent_status !== "granted") {
      this.setData({
        loading: false,
        loadError: "",
        deleteNotice,
        posts: [],
        metrics: buildFeedMetrics(),
      });
      wx.stopPullDownRefresh();
      return;
    }

    this.setData({
      loading: true,
      loadError: "",
      deleteNotice,
    });
    this.loadFeed(session);
  },

  async loadFeed(session) {
    try {
      const response = await fetchTreeholeFeed({
        accessToken: session.accessToken,
        limit: 30,
      });
      const posts = (response.posts || []).map((post) => normalizeTreeholePost(post));
      posts.forEach((post) => cacheTreeholePost(post));
      this.setData({
        loading: false,
        loadError: "",
        posts,
        metrics: buildFeedMetrics(posts),
      });
    } catch (error) {
      if (error && error.statusCode === 401) {
        clearStudentSession();
        wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
        return;
      }

      this.setData({
        loading: false,
        loadError: error.message || "树洞广场加载失败，请稍后重试。",
        posts: [],
        metrics: buildFeedMetrics(),
      });
    } finally {
      wx.stopPullDownRefresh();
    }
  },

  handleRetryLoad() {
    this.bootstrap();
  },

  handleCreateTap() {
    wx.navigateTo({ url: PAGE_ROUTES.TREEHOLE_CREATE });
  },

  handlePostTap(event) {
    const postId = Number(event.currentTarget.dataset.postId);
    const targetPost = this.data.posts.find((post) => post.postId === postId);
    if (!targetPost) {
      wx.showToast({
        title: "帖子详情暂不可用",
        icon: "none",
      });
      return;
    }

    cacheTreeholePost(targetPost);
    wx.navigateTo({ url: buildTreeholeDetailRoute(postId) });
  },

  async handleReactionTap(event) {
    const postId = Number(event.currentTarget.dataset.postId);
    const reactionType = event.currentTarget.dataset.reactionType;
    const postIndex = this.data.posts.findIndex((post) => post.postId === postId);
    if (postIndex < 0) {
      return;
    }

    const originalPost = this.data.posts[postIndex];
    if (hasReactedToTreehole(originalPost, reactionType)) {
      wx.showToast({
        title: "你已经表达过支持了",
        icon: "none",
      });
      return;
    }

    const currentSession = ensureAuthenticatedSession();
    if (!currentSession) {
      return;
    }

    const optimisticPost = applyOptimisticTreeholeReaction(
      originalPost,
      reactionType
    );
    const optimisticPosts = this.data.posts.slice();
    optimisticPosts[postIndex] = optimisticPost;
    this.setData({
      posts: optimisticPosts,
      metrics: buildFeedMetrics(optimisticPosts),
    });

    try {
      const reactionData = await submitTreeholeReaction({
        accessToken: currentSession.accessToken,
        postId,
        reactionType,
      });
      const nextPosts = this.data.posts.slice();
      const nextIndex = nextPosts.findIndex((post) => post.postId === postId);
      if (nextIndex >= 0) {
        nextPosts[nextIndex] = mergeTreeholeReactionResult(
          nextPosts[nextIndex],
          reactionData
        );
        cacheTreeholePost(nextPosts[nextIndex]);
        this.setData({
          posts: nextPosts,
          metrics: buildFeedMetrics(nextPosts),
        });
      }
    } catch (error) {
      if (error && error.statusCode === 401) {
        clearStudentSession();
        wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
        return;
      }

      const rollbackPosts = this.data.posts.slice();
      rollbackPosts[postIndex] = normalizeTreeholePost(originalPost, {
        isMine: originalPost.isMine,
        publishStatus: originalPost.publishStatus,
        riskLevel: originalPost.riskLevel,
      });
      this.setData({
        posts: rollbackPosts,
        metrics: buildFeedMetrics(rollbackPosts),
      });
      wx.showToast({
        title: error.message || "互动提交失败，请稍后重试。",
        icon: "none",
      });
    }
  },

  handleBackHome() {
    wx.reLaunch({ url: PAGE_ROUTES.HOME });
  },
});
