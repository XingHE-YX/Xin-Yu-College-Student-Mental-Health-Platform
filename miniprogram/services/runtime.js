const { request } = require("./request");

function normalizeRuntimeFeatures(features) {
  const payload = features || {};
  return {
    enableDemoLogin: Boolean(payload.enable_demo_login),
    enableMockAi: Boolean(payload.enable_mock_ai),
    showSeededCases: Boolean(payload.show_seeded_cases),
    demoModeEnabled: Boolean(payload.demo_mode_enabled),
  };
}

async function fetchRuntimeFeatures() {
  const data = await request({
    url: "/runtime/features",
    method: "GET",
  });
  return normalizeRuntimeFeatures(data);
}

module.exports = {
  fetchRuntimeFeatures,
  normalizeRuntimeFeatures,
};
