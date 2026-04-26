const { PAGE_ROUTES } = require("../constants/config");

const TREEHOLE_POST_CACHE_PREFIX = "xinyu_treehole_post_";
const TREEHOLE_RECENT_DELETE_NOTICE_KEY = "xinyu_treehole_recent_delete_notice";
const REACTION_ORDER = ["hug", "light", "accompany"];
const REACTION_LABELS = {
  hug: "抱抱",
  light: "点亮",
  accompany: "陪伴",
};
const PUBLISH_STATUS_LABELS = {
  published: "已公开",
  deleted_by_user: "已删除",
  blocked_high_risk: "未公开",
  hidden_by_admin: "已下线",
};

function getTreeholePostCacheKey(postId) {
  return `${TREEHOLE_POST_CACHE_PREFIX}${postId}`;
}

function padNumber(value) {
  return String(value).padStart(2, "0");
}

function parseTreeholeDate(value) {
  if (!value || typeof value !== "string") {
    return null;
  }

  const normalized = value.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date;
}

function formatTreeholeAbsoluteTime(value) {
  const date = parseTreeholeDate(value);
  if (!date) {
    return "时间未知";
  }

  return `${date.getFullYear()}-${padNumber(date.getMonth() + 1)}-${padNumber(
    date.getDate()
  )} ${padNumber(date.getHours())}:${padNumber(date.getMinutes())}`;
}

function formatTreeholeRelativeTime(value) {
  const date = parseTreeholeDate(value);
  if (!date) {
    return "刚刚";
  }

  const elapsed = Date.now() - date.getTime();
  if (elapsed < 60 * 1000) {
    return "刚刚";
  }
  if (elapsed < 60 * 60 * 1000) {
    return `${Math.max(1, Math.floor(elapsed / (60 * 1000)))} 分钟前`;
  }
  if (elapsed < 24 * 60 * 60 * 1000) {
    return `${Math.max(1, Math.floor(elapsed / (60 * 60 * 1000)))} 小时前`;
  }
  if (elapsed < 48 * 60 * 60 * 1000) {
    return `昨天 ${padNumber(date.getHours())}:${padNumber(date.getMinutes())}`;
  }

  return `${date.getMonth() + 1} 月 ${date.getDate()} 日 ${padNumber(
    date.getHours()
  )}:${padNumber(date.getMinutes())}`;
}

function normalizeTreeholeReactions(reactions = []) {
  const reactionByType = {};
  reactions.forEach((reaction) => {
    const reactionType = reaction.reactionType || reaction.reaction_type;
    if (!reactionType) {
      return;
    }

    reactionByType[reactionType] = {
      reactionType,
      label: reaction.label || REACTION_LABELS[reactionType] || "支持",
      count: Number(reaction.count || 0),
      reactedByMe:
        reaction.reactedByMe === true || reaction.reacted_by_me === true,
      busy: Boolean(reaction.busy),
    };
  });

  return REACTION_ORDER.map((reactionType) => {
    if (reactionByType[reactionType]) {
      return reactionByType[reactionType];
    }

    return {
      reactionType,
      label: REACTION_LABELS[reactionType],
      count: 0,
      reactedByMe: false,
      busy: false,
    };
  });
}

function normalizeTreeholePost(rawPost, extras = {}) {
  const publishedAt = rawPost.publishedAt || rawPost.published_at || "";
  const deletedAt = rawPost.deletedAt || rawPost.deleted_at || "";
  const reactions = normalizeTreeholeReactions(rawPost.reactions || []);
  const totalReactionCount = Number(
    rawPost.totalReactionCount ||
      rawPost.total_reaction_count ||
      reactions.reduce((sum, reaction) => sum + reaction.count, 0)
  );
  const publishStatus =
    rawPost.publishStatus ||
    rawPost.publish_status ||
    extras.publishStatus ||
    "published";

  return {
    postId: Number(rawPost.postId || rawPost.post_id),
    anonymousName:
      rawPost.anonymousName || rawPost.anonymous_name || "匿名同学",
    anonymousAvatarKey:
      rawPost.anonymousAvatarKey || rawPost.anonymous_avatar_key || "",
    content: rawPost.content || rawPost.content_masked || "",
    publishedAt,
    publishedAtLabel: formatTreeholeAbsoluteTime(publishedAt),
    relativeTime: formatTreeholeRelativeTime(publishedAt),
    deletedAt,
    deletedAtLabel: deletedAt ? formatTreeholeAbsoluteTime(deletedAt) : "",
    deletedAtChipLabel: deletedAt
      ? `删除时间：${formatTreeholeAbsoluteTime(deletedAt)}`
      : "删除时间已记录",
    isMine: rawPost.isMine === true || rawPost.is_mine === true || extras.isMine === true,
    totalReactionCount,
    reactions,
    publishStatus,
    publishStatusLabel:
      PUBLISH_STATUS_LABELS[publishStatus] || PUBLISH_STATUS_LABELS.published,
    riskLevel:
      rawPost.riskLevel || rawPost.risk_level || extras.riskLevel || "low",
    allowPublication:
      rawPost.allowPublication !== undefined
        ? rawPost.allowPublication
        : rawPost.allow_publication !== undefined
        ? rawPost.allow_publication
        : true,
    detailLinkLabel:
      publishStatus === "deleted_by_user"
        ? "已从学生端移除"
        : rawPost.isMine === true ||
          rawPost.is_mine === true ||
          extras.isMine === true
        ? "查看详情与删除"
        : "查看完整内容",
  };
}

function buildCreatedTreeholePost(rawPost) {
  return normalizeTreeholePost(rawPost, {
    isMine: true,
    publishStatus: rawPost.publish_status || "published",
    riskLevel: rawPost.risk_level || "low",
  });
}

function buildDeletedTreeholePost(rawPost, options = {}) {
  const deletedAt =
    options.deletedAt ||
    rawPost.deletedAt ||
    rawPost.deleted_at ||
    new Date().toISOString();

  return normalizeTreeholePost(
    {
      ...rawPost,
      content: "",
      content_masked: "",
      publish_status: "deleted_by_user",
      allow_publication: false,
      deleted_at: deletedAt,
    },
    {
      isMine: true,
      publishStatus: "deleted_by_user",
      riskLevel: rawPost.riskLevel || rawPost.risk_level || "low",
    }
  );
}

function cacheTreeholePost(post) {
  if (!post || !post.postId) {
    return;
  }

  try {
    wx.setStorageSync(getTreeholePostCacheKey(post.postId), post);
  } catch (error) {}
}

function loadCachedTreeholePost(postId) {
  if (!postId) {
    return null;
  }

  try {
    const cached = wx.getStorageSync(getTreeholePostCacheKey(postId));
    if (!cached || typeof cached !== "object") {
      return null;
    }
    return normalizeTreeholePost(cached, {
      isMine: cached.isMine,
      publishStatus: cached.publishStatus,
      riskLevel: cached.riskLevel,
    });
  } catch (error) {
    return null;
  }
}

function removeCachedTreeholePost(postId) {
  if (!postId) {
    return;
  }

  try {
    wx.removeStorageSync(getTreeholePostCacheKey(postId));
  } catch (error) {}
}

function buildTreeholeDetailRoute(postId) {
  return `${PAGE_ROUTES.TREEHOLE_DETAIL}?postId=${encodeURIComponent(postId)}`;
}

function setRecentTreeholeDeleteNotice(post) {
  if (!post || !post.postId) {
    return;
  }

  try {
    wx.setStorageSync(TREEHOLE_RECENT_DELETE_NOTICE_KEY, {
      postId: post.postId,
      deletedAt: post.deletedAt || "",
      message:
        "你删除的帖子已从学生端广场移除。后台仍会保留记录，以满足审计与复核需要。",
    });
  } catch (error) {}
}

function consumeRecentTreeholeDeleteNotice() {
  try {
    const storedNotice = wx.getStorageSync(TREEHOLE_RECENT_DELETE_NOTICE_KEY);
    wx.removeStorageSync(TREEHOLE_RECENT_DELETE_NOTICE_KEY);
    if (!storedNotice || typeof storedNotice !== "object") {
      return "";
    }

    return String(storedNotice.message || "").trim();
  } catch (error) {
    return "";
  }
}

function hasReactedToTreehole(post, reactionType) {
  if (!post || !Array.isArray(post.reactions)) {
    return false;
  }

  const targetReaction = post.reactions.find(
    (reaction) => reaction.reactionType === reactionType
  );
  return Boolean(targetReaction && targetReaction.reactedByMe);
}

function applyOptimisticTreeholeReaction(post, reactionType) {
  const normalizedPost = normalizeTreeholePost(post, {
    isMine: post.isMine,
    publishStatus: post.publishStatus,
    riskLevel: post.riskLevel,
  });
  if (hasReactedToTreehole(normalizedPost, reactionType)) {
    return normalizedPost;
  }

  return {
    ...normalizedPost,
    totalReactionCount: normalizedPost.totalReactionCount + 1,
    reactions: normalizedPost.reactions.map((reaction) => {
      if (reaction.reactionType !== reactionType) {
        return {
          ...reaction,
          busy: false,
        };
      }

      return {
        ...reaction,
        count: reaction.count + 1,
        reactedByMe: true,
        busy: true,
      };
    }),
  };
}

function mergeTreeholeReactionResult(post, reactionData) {
  return normalizeTreeholePost(
    {
      ...post,
      total_reaction_count: reactionData.total_reaction_count,
      reactions: reactionData.reactions,
    },
    {
      isMine: post.isMine,
      publishStatus: post.publishStatus,
      riskLevel: post.riskLevel,
    }
  );
}

module.exports = {
  applyOptimisticTreeholeReaction,
  buildCreatedTreeholePost,
  buildDeletedTreeholePost,
  buildTreeholeDetailRoute,
  cacheTreeholePost,
  consumeRecentTreeholeDeleteNotice,
  formatTreeholeAbsoluteTime,
  formatTreeholeRelativeTime,
  hasReactedToTreehole,
  loadCachedTreeholePost,
  mergeTreeholeReactionResult,
  normalizeTreeholePost,
  removeCachedTreeholePost,
  setRecentTreeholeDeleteNotice,
};
