const API_BASE_URL = "http://127.0.0.1:8000/api/v1";
const CONSENT_VERSION = "v1.0";
const HOTLINE_PHONE = "400-161-9995";
const PAGE_ROUTES = {
  STARTUP: "/pages/startup/index",
  LOGIN: "/pages/login/index",
  CONSENT: "/pages/consent/index",
  HOME: "/pages/home/index",
  TREEHOLE_FEED: "/pages/treehole/feed/index",
  TREEHOLE_CREATE: "/pages/treehole/create/index",
  TREEHOLE_DETAIL: "/pages/treehole/detail/index",
  QUESTIONNAIRE_SCREEN: "/pages/questionnaires/screen/index",
  QUESTIONNAIRE_SDS: "/pages/questionnaires/sds/index",
  QUESTIONNAIRE_SAS: "/pages/questionnaires/sas/index",
  QUESTIONNAIRE_SLEEP: "/pages/questionnaires/sleep/index",
  QUESTIONNAIRE_UPI: "/pages/questionnaires/upi/index",
  REPORT_SUMMARY: "/pages/reports/index",
  REPORT_FULL: "/pages/reports/full/index",
};

function buildDefaultRuntimeFeatures() {
  return {
    enableDemoLogin: false,
    enableMockAi: false,
    showSeededCases: false,
    demoModeEnabled: false,
  };
}

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
  buildDefaultRuntimeFeatures,
  CONSENT_VERSION,
  HOTLINE_PHONE,
  PAGE_ROUTES,
  shouldShowDemoEntry,
};
