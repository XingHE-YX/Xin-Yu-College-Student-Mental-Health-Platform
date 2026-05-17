const { PAGE_ROUTES } = require("../constants/config");

const PRIMARY_TAB_ROUTE_SET = new Set([
  PAGE_ROUTES.HOME,
  PAGE_ROUTES.REPORT_SUMMARY,
  PAGE_ROUTES.TREEHOLE_FEED,
  PAGE_ROUTES.PROFILE,
]);

function isPrimaryTabRoute(route) {
  return PRIMARY_TAB_ROUTE_SET.has(route);
}

function switchToPrimaryTab(route) {
  if (!isPrimaryTabRoute(route)) {
    return Promise.reject(new Error(`'${route}' is not a primary tab route`));
  }

  return new Promise((resolve, reject) => {
    wx.switchTab({
      url: route,
      success: resolve,
      fail: reject,
    });
  });
}

function relaunchOrSwitchTab(route) {
  if (isPrimaryTabRoute(route)) {
    return switchToPrimaryTab(route);
  }

  return new Promise((resolve, reject) => {
    wx.reLaunch({
      url: route,
      success: resolve,
      fail: reject,
    });
  });
}

function redirectOrSwitchTab(route) {
  if (isPrimaryTabRoute(route)) {
    return switchToPrimaryTab(route);
  }

  return new Promise((resolve, reject) => {
    wx.redirectTo({
      url: route,
      success: resolve,
      fail: reject,
    });
  });
}

module.exports = {
  isPrimaryTabRoute,
  relaunchOrSwitchTab,
  redirectOrSwitchTab,
  switchToPrimaryTab,
};
