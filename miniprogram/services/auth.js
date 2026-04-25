const { CONSENT_VERSION } = require("../constants/config");
const { request } = require("./request");

function buildPhoneTicket(form) {
  return JSON.stringify({
    phone_number: form.phoneNumber,
    college_name: form.collegeName,
    class_name: form.className,
  });
}

function loginWithWechat(payload) {
  return request({
    url: "/auth/student/wechat-login",
    method: "POST",
    data: {
      login_code: payload.loginCode,
      phone_ticket: buildPhoneTicket(payload),
      phone_signature: null,
    },
  });
}

function loginWithDemo() {
  return request({
    url: "/auth/student/demo-login",
    method: "POST",
  });
}

function submitConsent(options) {
  return request({
    url: "/consents",
    method: "POST",
    token: options.accessToken,
    data: {
      consent_type: options.consentType,
      consent_version: options.consentVersion || CONSENT_VERSION,
      granted: options.granted,
    },
  });
}

module.exports = {
  loginWithDemo,
  loginWithWechat,
  submitConsent,
};
