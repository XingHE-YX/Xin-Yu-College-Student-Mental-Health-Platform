const { HOTLINE_PHONE, PAGE_ROUTES } = require("../../constants/config");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../utils/session");

Page({
  data: {
    hotlinePhone: HOTLINE_PHONE,
  },

  onShow() {
    const session = loadStudentSession();
    if (!hasValidStudentSession(session)) {
      clearStudentSession();
      wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
      return;
    }
  },

  handleCallHotline() {
    wx.makePhoneCall({
      phoneNumber: this.data.hotlinePhone,
      fail: () => {
        wx.showToast({
          title: "拨号失败，请手动联系热线",
          icon: "none",
        });
      },
    });
  },

  handleBackProfile() {
    wx.navigateBack({
      fail() {
        wx.reLaunch({ url: PAGE_ROUTES.PROFILE });
      },
    });
  },
});
