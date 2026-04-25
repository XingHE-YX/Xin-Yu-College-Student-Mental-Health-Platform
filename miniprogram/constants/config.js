const API_BASE_URL = "http://127.0.0.1:8000/api/v1";
const CONSENT_VERSION = "v1.0";
const HOTLINE_PHONE = "400-161-9995";
const PAGE_ROUTES = {
  STARTUP: "/pages/startup/index",
  LOGIN: "/pages/login/index",
  CONSENT: "/pages/consent/index",
  HOME: "/pages/home/index",
};

function shouldShowDemoEntry() {
  try {
    const accountInfo = wx.getAccountInfoSync();
    return accountInfo.miniProgram.envVersion !== "release";
  } catch (error) {
    return true;
  }
}

module.exports = {
  API_BASE_URL,
  CONSENT_VERSION,
  HOTLINE_PHONE,
  PAGE_ROUTES,
  shouldShowDemoEntry,
};
