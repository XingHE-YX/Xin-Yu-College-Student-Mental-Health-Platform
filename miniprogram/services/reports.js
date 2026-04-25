const { request } = require("./request");

function fetchReportSummary(options) {
  return request({
    url: "/reports/summary",
    token: options.accessToken,
  });
}

function fetchFullReport(options) {
  return request({
    url: "/reports/full",
    token: options.accessToken,
  });
}

function fetchReportHistory(options) {
  return request({
    url: "/reports/history",
    token: options.accessToken,
  });
}

module.exports = {
  fetchFullReport,
  fetchReportHistory,
  fetchReportSummary,
};
