const { API_BASE_URL } = require("../constants/config");

function request(options) {
  const {
    url,
    method = "GET",
    data,
    token,
    header = {},
  } = options;

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE_URL}${url}`,
      method,
      data,
      timeout: 10000,
      header: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...header,
      },
      success(response) {
        const { statusCode } = response;
        const body = response.data || {};

        if (statusCode >= 200 && statusCode < 300) {
          if (
            body &&
            typeof body === "object" &&
            body.code === "OK" &&
            Object.prototype.hasOwnProperty.call(body, "data")
          ) {
            resolve(body.data);
            return;
          }

          resolve(body);
          return;
        }

        reject({
          statusCode,
          code: body.code || "REQUEST_FAILED",
          message: body.message || "请求失败，请稍后重试。",
          requestId: body.request_id || "",
        });
      },
      fail(error) {
        reject({
          statusCode: 0,
          code: "NETWORK_ERROR",
          message: "无法连接到服务，请确认本地后端已启动且开发域名已放行。",
          rawError: error,
        });
      },
    });
  });
}

module.exports = {
  request,
};
