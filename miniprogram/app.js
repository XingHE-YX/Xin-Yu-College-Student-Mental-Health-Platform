const { API_BASE_URL, shouldShowDemoEntry } = require("./constants/config");
const {
  clearStudentSession,
  loadStudentSession,
  saveStudentSession,
} = require("./utils/session");

App({
  globalData: {
    appName: "心语",
    apiBaseUrl: API_BASE_URL,
    enableDemoEntry: true,
    studentSession: null,
  },

  onLaunch() {
    this.globalData.enableDemoEntry = shouldShowDemoEntry();
    this.globalData.studentSession = loadStudentSession();
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
});
