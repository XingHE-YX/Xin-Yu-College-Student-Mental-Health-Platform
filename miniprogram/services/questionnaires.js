const { request } = require("./request");

function fetchQuestionnaireList(options) {
  return request({
    url: "/questionnaires",
    token: options.accessToken,
  });
}

function fetchQuestionnaireDetail(options) {
  return request({
    url: `/questionnaires/${encodeURIComponent(options.code)}`,
    token: options.accessToken,
  });
}

function fetchRequiredProgress(options) {
  return request({
    url: "/questionnaires/progress",
    token: options.accessToken,
  });
}

module.exports = {
  fetchQuestionnaireDetail,
  fetchQuestionnaireList,
  fetchRequiredProgress,
};
