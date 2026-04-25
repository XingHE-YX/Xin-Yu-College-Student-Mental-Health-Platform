const { PAGE_ROUTES } = require("../../constants/config");
const {
  clearStudentSession,
  hasValidStudentSession,
  loadStudentSession,
} = require("../../utils/session");

function buildModules(student) {
  const treeholeDisabled = student.consent_status !== "granted";
  return [
    {
      key: "screen",
      title: "快速筛查",
      meta: "15 题起步",
      metaTone: "default",
      summary: "先用 15 道题完成轻量筛查，后续量表将在第 7 阶段逐步接入。",
      hint: "将在 7.3 阶段开放完整问卷页",
      disabled: false,
    },
    {
      key: "assessment",
      title: "深度测评中心",
      meta: "SDS / SAS / 睡眠",
      metaTone: "default",
      summary: "完成四份必做问卷后，完整报告会按 70 题链路自动解锁。",
      hint: "接口与页面将在后续步骤接入",
      disabled: false,
    },
    {
      key: "report",
      title: "我的报告",
      meta: "0 / 70",
      metaTone: "warning",
      summary: "当前报告仍处于锁定状态。完成必做问卷后，可查看综合画像与调节建议。",
      hint: "报告页骨架已完成，问卷接入后会显示真实进度",
      disabled: false,
    },
    {
      key: "treehole",
      title: "树洞",
      meta: treeholeDisabled ? "暂不可用" : "可进入",
      metaTone: treeholeDisabled ? "disabled" : "default",
      summary: treeholeDisabled
        ? "你当前拒绝了危机干预授权，因此树洞入口会保持禁用。"
        : "授权已完成，树洞入口会在后续步骤接入内容发布与广场页。",
      hint: treeholeDisabled
        ? "拒绝授权不会影响测评与报告功能"
        : "将在第 8 阶段接入树洞流程",
      disabled: treeholeDisabled,
    },
    {
      key: "help",
      title: "帮助资源",
      meta: "静态资源",
      metaTone: "default",
      summary: "求助电话、呼吸调节建议与校内心理中心信息会放在帮助页统一展示。",
      hint: "将在后续步骤开放帮助资源页",
      disabled: false,
    },
  ];
}

Page({
  data: {
    student: null,
    modules: [],
    consentDeclined: false,
  },

  onShow() {
    this.bootstrap();
  },

  bootstrap() {
    try {
      const session = loadStudentSession();
      if (!hasValidStudentSession(session)) {
        clearStudentSession();
        wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
        return;
      }

      getApp().globalData.studentSession = session;
      if (session.student.consent_status === "missing") {
        wx.reLaunch({ url: PAGE_ROUTES.CONSENT });
        return;
      }

      this.setData({
        student: session.student,
        consentDeclined: session.student.consent_status === "declined",
        modules: buildModules(session.student),
      });
    } catch (error) {
      clearStudentSession();
      wx.reLaunch({ url: PAGE_ROUTES.LOGIN });
    }
  },

  handleModuleTap(event) {
    const { key, disabled } = event.currentTarget.dataset;
    if (disabled) {
      wx.showToast({
        title: "当前入口受授权状态限制",
        icon: "none",
      });
      return;
    }

    const titles = {
      screen: "快速筛查将在后续步骤接入",
      assessment: "深度测评中心将在后续步骤接入",
      report: "报告详情将在后续步骤接入",
      treehole: "树洞流程将在后续步骤接入",
      help: "帮助资源页将在后续步骤接入",
    };

    wx.showToast({
      title: titles[key] || "该功能将在后续步骤接入",
      icon: "none",
    });
  },
});
