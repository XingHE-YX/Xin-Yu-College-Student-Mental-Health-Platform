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
const {
  switchToPrimaryTab,
} = require("../../../utils/navigation");
const {
  readChannelCache,
  shouldRefreshChannel,
  writeChannelCache,
} = require("../../../utils/channel-sync");

const REACTION_TOAST_LABELS = {
  hug: "抱抱",
  light: "点亮",
  accompany: "陪伴",
};

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

function buildTreeholeFeedState(posts = []) {
  const metrics = buildFeedMetrics(posts);
  return {
    posts,
    metrics,
    feedSummary: buildFeedSummary(metrics),
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
    feedSummary: buildFeedSummary(buildFeedMetrics()),
    reactionSubmitting: false,
    reactionBusyKey: "",
  },

  onShow() {
    this.syncPrimaryTabBar();
    if (this.skipNextOnShowRefresh) {
      this.skipNextOnShowRefresh = false;
      return;
    }
    if (this.hasBootstrapped) {
      this.bootstrap({ preserveContent: true });
      return;
    }
    this.bootstrap();
  },

  onUnload() {
    this.latestFeedRequestId = (this.latestFeedRequestId || 0) + 1;
  },

  onPullDownRefresh() {
    this.bootstrap();
  },

  onLoad() {
    this.skipNextOnShowRefresh = true;
  },

  bootstrap(options = {}) {
    const preserveContent = Boolean(options.preserveContent);
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
      this.hasBootstrapped = true;
      return;
    }

    const shouldRefresh = shouldRefreshChannel("treehole", {
      force: options.forceRefresh === true || !preserveContent,
    });
    const cachedPayload = preserveContent ? readChannelCache("treehole") : null;

    if (cachedPayload) {
      this.setData({
        ...buildTreeholeFeedState(cachedPayload.posts || []),
        student: session.student,
        feedDisabled: false,
        loading: false,
        loadError: "",
        deleteNotice,
      });
    } else {
      this.setData(
        preserveContent
          ? {
              loadError: "",
              deleteNotice,
            }
          : {
              loading: true,
              loadError: "",
              deleteNotice,
            }
      );
    }
    this.hasBootstrapped = true;
    if (!shouldRefresh) {
      wx.stopPullDownRefresh();
      return;
    }
    this.loadFeed(session);
  },

  async loadFeed(session) {
    const requestId = (this.latestFeedRequestId || 0) + 1;
    this.latestFeedRequestId = requestId;

    try {
      const response = await fetchTreeholeFeed({
        accessToken: session.accessToken,
        limit: 30,
      });
      if (requestId !== this.latestFeedRequestId) {
        return;
      }
      const posts = (response.posts || []).map((post) => normalizeTreeholePost(post));
      posts.forEach((post) => cacheTreeholePost(post));
      writeChannelCache("treehole", {
        posts,
      });
      this.setData({
        loading: false,
        loadError: "",
        ...buildTreeholeFeedState(posts),
      });
    } catch (error) {
      if (requestId !== this.latestFeedRequestId) {
        return;
      }
      if (error && error.statusCode === 401) {
        clearStudentSession();
        wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
        return;
      }

      const hasCachedPosts = Array.isArray(this.data.posts) && this.data.posts.length > 0;
      if (hasCachedPosts) {
        this.setData({
          loading: false,
          loadError: error.message || "树洞广场加载失败，请稍后重试。",
        });
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
    if (
      postIndex < 0 ||
      !reactionType ||
      this.data.reactionSubmitting ||
      this.feedReactionRequestInFlight
    ) {
      return;
    }

    const originalPost = this.data.posts[postIndex];
    const wasReacted = hasReactedToTreehole(originalPost, reactionType);
    const reactionLabel = REACTION_TOAST_LABELS[reactionType] || "支持";

    const currentSession = ensureAuthenticatedSession();
    if (!currentSession) {
      return;
    }

    this.feedReactionRequestInFlight = true;
    const reactionBusyKey = `${postId}:${reactionType}`;
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
      reactionSubmitting: true,
      reactionBusyKey,
    });
    writeChannelCache("treehole", {
      posts: optimisticPosts,
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
          reactionSubmitting: false,
          reactionBusyKey: "",
        });
        writeChannelCache("treehole", {
          posts: nextPosts,
        });
      } else {
        this.setData({
          reactionSubmitting: false,
          reactionBusyKey: "",
        });
      }
      this.feedReactionRequestInFlight = false;
    } catch (error) {
      this.feedReactionRequestInFlight = false;
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
        reactionSubmitting: false,
        reactionBusyKey: "",
      });
      writeChannelCache("treehole", {
        posts: rollbackPosts,
      });
      wx.showToast({
        title: error.message || "互动提交失败，请稍后重试。",
        icon: "none",
      });
      return;
    }

    wx.showToast({
      title: wasReacted ? `已取消${reactionLabel}` : `已${reactionLabel}`,
      icon: "none",
    });
  },

  handleBackHome() {
    switchToPrimaryTab(PAGE_ROUTES.HOME);
  },

  handleChannelChange(event) {
    const { key } = event.detail || {};
    const route = getPrimaryChannelRoute(key);
    if (!route || route === PAGE_ROUTES.TREEHOLE_FEED) {
      return;
    }
    switchToPrimaryTab(route);
  },

  syncPrimaryTabBar() {
    if (typeof this.getTabBar !== "function") {
      return;
    }
    const tabBar = this.getTabBar();
    if (tabBar && typeof tabBar.setActiveByRoute === "function") {
      tabBar.setActiveByRoute(PAGE_ROUTES.TREEHOLE_FEED);
    }
  },
});
