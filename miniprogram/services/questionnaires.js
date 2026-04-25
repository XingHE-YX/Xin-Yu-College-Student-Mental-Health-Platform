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

function submitQuestionnaire(options) {
  return request({
    url: `/questionnaires/${encodeURIComponent(options.code)}/submissions`,
    method: "POST",
    token: options.accessToken,
    data: {
      answers: options.answers,
    },
  });
}

module.exports = {
  fetchQuestionnaireDetail,
  fetchQuestionnaireList,
  fetchRequiredProgress,
  submitQuestionnaire,
};
