const CHANNEL_REFRESH_TTLS = {
  assessment: 60 * 1000,
  report: 60 * 1000,
  treehole: 20 * 1000,
};

function getChannelSyncState(appInstance) {
  const app = appInstance || getApp();
  if (!app.globalData.channelSync) {
    app.globalData.channelSync = {
      cache: {},
      dirty: {},
      lastFetchedAt: {},
    };
  }
  return app.globalData.channelSync;
}

function readChannelCache(channelKey) {
  const state = getChannelSyncState();
  return state.cache[channelKey] || null;
}

function writeChannelCache(channelKey, payload) {
  const state = getChannelSyncState();
  state.cache[channelKey] = payload;
  state.lastFetchedAt[channelKey] = Date.now();
  state.dirty[channelKey] = false;
}

function markChannelDirty(channelKey) {
  const state = getChannelSyncState();
  state.dirty[channelKey] = true;
}

function markChannelsDirty(channelKeys = []) {
  channelKeys.forEach((channelKey) => {
    markChannelDirty(channelKey);
  });
}

function isChannelDirty(channelKey) {
  const state = getChannelSyncState();
  return state.dirty[channelKey] === true;
}

function getChannelLastFetchedAt(channelKey) {
  const state = getChannelSyncState();
  return Number(state.lastFetchedAt[channelKey] || 0);
}

function shouldRefreshChannel(channelKey, options = {}) {
  if (options.force === true) {
    return true;
  }

  if (isChannelDirty(channelKey)) {
    return true;
  }

  const ttl = CHANNEL_REFRESH_TTLS[channelKey] || 0;
  if (!ttl) {
    return false;
  }

  const lastFetchedAt = getChannelLastFetchedAt(channelKey);
  if (!lastFetchedAt) {
    return true;
  }

  return Date.now() - lastFetchedAt >= ttl;
}

module.exports = {
  markChannelDirty,
  markChannelsDirty,
  readChannelCache,
  shouldRefreshChannel,
  writeChannelCache,
};
