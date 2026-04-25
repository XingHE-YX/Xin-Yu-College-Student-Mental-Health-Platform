const { STORAGE_KEYS } = require("../constants/storage");

function decodeAccessTokenPayload(accessToken) {
  if (!accessToken || typeof accessToken !== "string") {
    return null;
  }

  const segments = accessToken.split(".");
  if (segments.length !== 3) {
    return null;
  }

  const payloadSegment = segments[1];
  const normalizedSegment = payloadSegment
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const padding = "=".repeat((4 - (normalizedSegment.length % 4)) % 4);

  try {
    const payloadText = wx.base64ToArrayBuffer(normalizedSegment + padding);
    const decodedText = String.fromCharCode.apply(
      null,
      new Uint8Array(payloadText)
    );
    return JSON.parse(decodedText);
  } catch (error) {
    return null;
  }
}

function normalizeSessionPayload(sessionData) {
  if (!sessionData || !sessionData.access_token || !sessionData.student) {
    return null;
  }

  const tokenPayload = decodeAccessTokenPayload(sessionData.access_token);
  const expiresAt =
    tokenPayload && typeof tokenPayload.exp === "number"
      ? tokenPayload.exp * 1000
      : null;

  return {
    accessToken: sessionData.access_token,
    student: sessionData.student,
    expiresAt,
  };
}

function saveStudentSession(sessionData) {
  const normalizedSession = normalizeSessionPayload(sessionData);
  if (!normalizedSession) {
    throw new Error("invalid student session payload");
  }

  wx.setStorageSync(STORAGE_KEYS.STUDENT_SESSION, normalizedSession);
  return normalizedSession;
}

function loadStudentSession() {
  const storedSession = wx.getStorageSync(STORAGE_KEYS.STUDENT_SESSION);
  if (
    !storedSession ||
    typeof storedSession !== "object" ||
    !storedSession.accessToken ||
    !storedSession.student
  ) {
    return null;
  }
  return storedSession;
}

function clearStudentSession() {
  wx.removeStorageSync(STORAGE_KEYS.STUDENT_SESSION);
}

function hasValidStudentSession(session = loadStudentSession()) {
  if (!session || !session.accessToken || !session.student) {
    return false;
  }

  if (typeof session.expiresAt !== "number") {
    return true;
  }

  return session.expiresAt > Date.now() + 15 * 1000;
}

module.exports = {
  clearStudentSession,
  decodeAccessTokenPayload,
  hasValidStudentSession,
  loadStudentSession,
  normalizeSessionPayload,
  saveStudentSession,
};
