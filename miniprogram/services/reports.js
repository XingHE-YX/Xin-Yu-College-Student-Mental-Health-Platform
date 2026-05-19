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

function deleteReportHistoryItem(options) {
  return request({
    url: `/reports/history/${encodeURIComponent(options.submissionId)}`,
    method: "DELETE",
    token: options.accessToken,
  });
}

module.exports = {
  deleteReportHistoryItem,
  fetchFullReport,
  fetchReportHistory,
  fetchReportSummary,
};
