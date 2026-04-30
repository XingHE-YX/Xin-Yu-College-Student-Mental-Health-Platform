const {
  API_BASE_URL,
  buildDefaultRuntimeFeatures,
} = require("./constants/config");
const { fetchRuntimeFeatures } = require("./services/runtime");
const {
  clearStudentSession,
  loadStudentSession,
  saveStudentSession,
} = require("./utils/session");

App({
  globalData: {
    appName: "心语",
    apiBaseUrl: API_BASE_URL,
    enableDemoEntry: false,
    runtimeFeatures: buildDefaultRuntimeFeatures(),
    studentSession: null,
  },

  onLaunch() {
    this.globalData.studentSession = loadStudentSession();
    this.syncRuntimeFeatures();
  },

  setStudentSession(sessionData) {
    const session = saveStudentSession(sessionData);
    this.globalData.studentSession = session;
    return session;
  },

  getStudentSession() {
    if (this.globalData.studentSession) {
      return this.globalData.studentSession;
    }

    const session = loadStudentSession();
    this.globalData.studentSession = session;
    return session;
  },

  clearStudentSession() {
    clearStudentSession();
    this.globalData.studentSession = null;
  },

  syncRuntimeFeatures() {
    if (this.runtimeFeaturesPromise) {
      return this.runtimeFeaturesPromise;
    }

    this.runtimeFeaturesPromise = fetchRuntimeFeatures()
      .then((features) => {
        this.globalData.runtimeFeatures = features;
        this.globalData.enableDemoEntry = features.enableDemoLogin;
        return features;
      })
      .catch(() => {
        const fallbackFeatures = buildDefaultRuntimeFeatures();
        this.globalData.runtimeFeatures = fallbackFeatures;
        this.globalData.enableDemoEntry = fallbackFeatures.enableDemoLogin;
        return fallbackFeatures;
      })
      .finally(() => {
        this.runtimeFeaturesPromise = null;
      });

    return this.runtimeFeaturesPromise;
  },
});
