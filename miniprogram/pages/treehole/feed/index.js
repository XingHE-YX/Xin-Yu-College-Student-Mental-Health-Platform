const { PAGE_ROUTES } = require("../../../constants/config");
const { getPrimaryChannelRoute } = require("../../../constants/navigation");
const {
  fetchTreeholeFeed,
  toggleTreeholeReaction,
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

function buildFeedSummary(metrics) {
  if (!metrics.publicCount) {
    return "广场还没有公开帖子。你可以先写下第一条匿名心情。";
  }
  return `当前有 ${metrics.publicCount} 条公开帖子，其中 ${metrics.myCount} 条来自你自己，累计 ${metrics.supportCount} 次支持反馈。`;
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
    feedSummary: buildFeedSummary(buildFeedMetrics()),
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
        feedSummary:
          "你当前还没有开放危机干预授权，因此树洞频道会保持禁用状态。",
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
        feedSummary: buildFeedSummary(buildFeedMetrics(posts)),
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
        feedSummary: "广场暂时未能同步。你可以稍后重试，或先写下新的匿名心情。",
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
    const wasReacted = hasReactedToTreehole(originalPost, reactionType);

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
      feedSummary: buildFeedSummary(buildFeedMetrics(optimisticPosts)),
    });

    try {
      const reactionData = await toggleTreeholeReaction({
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
          feedSummary: buildFeedSummary(buildFeedMetrics(nextPosts)),
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
        feedSummary: buildFeedSummary(buildFeedMetrics(rollbackPosts)),
      });
      wx.showToast({
        title: error.message || "互动提交失败，请稍后重试。",
        icon: "none",
      });
      return;
    }

    wx.showToast({
      title: wasReacted ? "已取消支持" : "已表达支持",
      icon: "none",
    });
  },

  handleBackHome() {
    wx.reLaunch({ url: PAGE_ROUTES.HOME });
  },

  handleChannelChange(event) {
    const { key } = event.detail || {};
    const route = getPrimaryChannelRoute(key);
    if (!route || route === PAGE_ROUTES.TREEHOLE_FEED) {
      return;
    }
    wx.reLaunch({ url: route });
  },
});
