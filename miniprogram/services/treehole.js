const { request } = require("./request");

function fetchTreeholeFeed(options) {
  return request({
    url: "/treehole/feed",
    token: options.accessToken,
    data: {
      limit: options.limit || 20,
    },
  });
}

function createTreeholePost(options) {
  return request({
    url: "/treehole/posts",
    method: "POST",
    token: options.accessToken,
    data: {
      content: options.content,
    },
  });
}

function deleteTreeholePost(options) {
  return request({
    url: `/treehole/posts/${encodeURIComponent(options.postId)}`,
    method: "DELETE",
    token: options.accessToken,
  });
}

function submitTreeholeReaction(options) {
  return request({
    url: `/treehole/posts/${encodeURIComponent(options.postId)}/reactions`,
    method: "POST",
    token: options.accessToken,
    data: {
      reaction_type: options.reactionType,
    },
  });
}

function toggleTreeholeReaction(options) {
  return submitTreeholeReaction(options);
}

module.exports = {
  createTreeholePost,
  deleteTreeholePost,
  fetchTreeholeFeed,
  submitTreeholeReaction,
  toggleTreeholeReaction,
};
