const { PAGE_ROUTES } = require("./config");

const QUESTIONNAIRE_PAGE_CONFIG = {
  SCREEN: {
    code: "SCREEN",
    name: "快速筛查",
    route: PAGE_ROUTES.QUESTIONNAIRE_SCREEN,
    pageStep: "S05",
    heroEyebrow: "S05 Quick Screen",
    heroTitle: "先完成最近一周的轻量筛查",
    heroSummary:
      "共 15 题，聚焦最近一周的情绪、压力和精力状态。它用于帮助你快速建立起点，不构成诊断结论。",
    scaleLabel: "1 - 5 频率量表",
    scoreLabel: "总分",
    unlockRequired: true,
    optionalHint: "",
    disclaimer:
      "这份结果用于帮助你理解最近一周的状态变化，不构成医学诊断或治疗建议。",
    latestHint:
      "你此前已经完成过一份快速筛查。若再次提交，首页和后续报告会以最新结果为准。",
    resultCopy: {
      low: {
        title: "当前筛查结果较平稳",
        summary:
          "这份轻量筛查暂未显示出明显的高压信号。若你仍想更完整地了解自己，可以继续完成后续必做量表。",
      },
      watch: {
        title: "当前筛查提示需要进一步关注",
        summary:
          "这份轻量筛查提示你最近一周可能承受着一定情绪或压力负担。建议继续完成 SDS、SAS 和睡眠问卷，让结果更完整。",
      },
      high: {
        title: "当前筛查提示需要优先留意自身状态",
        summary:
          "本次作答出现了较高强度的风险信号。请先关注当下安全与支持资源，并尽快联系可信赖的人。",
      },
    },
    nextCode: "SDS",
    nextLabel: "继续进入 SDS",
    homeLabel: "返回首页查看进度",
  },
  SDS: {
    code: "SDS",
    name: "SDS 抑郁自评量表",
    route: PAGE_ROUTES.QUESTIONNAIRE_SDS,
    pageStep: "S06",
    heroEyebrow: "S06 SDS",
    heroTitle: "继续完成 SDS 抑郁量表",
    heroSummary:
      "共 20 题，采用 4 级频率选项并换算为标准分。结果用于帮助你了解近期抑郁相关体验的强度变化。",
    scaleLabel: "4 级频率量表",
    scoreLabel: "标准分",
    unlockRequired: true,
    optionalHint: "",
    disclaimer:
      "SDS 结果用于自我了解和校园筛查，不构成临床诊断；如持续感到吃力，请考虑寻求专业支持。",
    latestHint:
      "你此前已经完成过一份 SDS。若再次提交，系统会以最新结果参与首页进度和后续报告。",
    resultCopy: {
      low: {
        title: "当前 SDS 结果较平稳",
        summary:
          "这次 SDS 标准分落在较平稳区间。若你近期仍感到明显吃力，也可以继续完成后续问卷获取更完整的画像。",
      },
      watch: {
        title: "当前 SDS 结果提示需要关注",
        summary:
          "这次 SDS 标准分提示你近期可能存在一定程度的低落或耗竭体验。建议继续完成后续问卷，并留意作息和支持网络。",
      },
      high: {
        title: "当前 SDS 结果提示需要优先关注",
        summary:
          "这次 SDS 作答提示你近期可能承受较重的情绪负荷。请尽量不要独自承受，优先联系可信赖的人或校园支持资源。",
      },
    },
    nextCode: "SAS",
    nextLabel: "继续进入 SAS",
    homeLabel: "返回首页查看进度",
  },
  SAS: {
    code: "SAS",
    name: "SAS 焦虑自评量表",
    route: PAGE_ROUTES.QUESTIONNAIRE_SAS,
    pageStep: "S07",
    heroEyebrow: "S07 SAS",
    heroTitle: "继续完成 SAS 焦虑量表",
    heroSummary:
      "共 20 题，采用 4 级频率选项并换算为标准分。结果用于帮助你识别近期焦虑和紧张体验的强度变化。",
    scaleLabel: "4 级频率量表",
    scoreLabel: "标准分",
    unlockRequired: true,
    optionalHint: "",
    disclaimer:
      "SAS 结果用于校园筛查和自我理解，不构成医学诊断；如紧张或不安持续加重，请尽快寻求支持。",
    latestHint:
      "你此前已经完成过一份 SAS。若再次提交，系统会以最新结果参与首页进度和后续报告。",
    resultCopy: {
      low: {
        title: "当前 SAS 结果较平稳",
        summary:
          "这次 SAS 标准分落在较平稳区间。保持基本作息和节奏即可，若仍担心近期状态，也可以继续完成后续问卷。",
      },
      watch: {
        title: "当前 SAS 结果提示需要关注",
        summary:
          "这次 SAS 标准分提示你近期可能存在一定焦虑或紧绷体验。建议继续完成睡眠问卷，帮助系统补齐完整画像。",
      },
      high: {
        title: "当前 SAS 结果提示需要优先关注",
        summary:
          "这次 SAS 作答提示你近期的紧张和不安可能已经较明显。请优先照顾当下状态，并尽快联系可信赖的人或校园支持资源。",
      },
    },
    nextCode: "SLEEP",
    nextLabel: "继续进入睡眠问卷",
    homeLabel: "返回首页查看进度",
  },
  SLEEP: {
    code: "SLEEP",
    name: "睡眠问卷",
    route: PAGE_ROUTES.QUESTIONNAIRE_SLEEP,
    pageStep: "S08",
    heroEyebrow: "S08 Sleep",
    heroTitle: "补齐最近一周的睡眠与作息状态",
    heroSummary:
      "共 15 题，采用 0 - 3 的频率量表，帮助你了解最近一周的入睡、醒来和恢复感受。",
    scaleLabel: "0 - 3 频率量表",
    scoreLabel: "总分",
    unlockRequired: true,
    optionalHint: "",
    disclaimer:
      "睡眠问卷结果用于帮助你了解近期作息状态，不构成医学诊断；若长期影响学习和生活，请考虑寻求专业支持。",
    latestHint:
      "你此前已经完成过一份睡眠问卷。若再次提交，系统会以最新结果参与首页进度和后续报告。",
    resultCopy: {
      low: {
        title: "当前睡眠状态较平稳",
        summary:
          "这次睡眠问卷未显示出明显的作息压力信号。返回首页后，你可以查看 70 题链路是否已经解锁完整报告。",
      },
      watch: {
        title: "当前睡眠状态提示需要关注",
        summary:
          "这次睡眠问卷提示你近期的作息或恢复感可能已有一定波动。保持规律作息，并在首页继续查看整体进度与结果。",
      },
      high: {
        title: "当前睡眠状态提示需要优先关注",
        summary:
          "这次睡眠作答提示你近期可能存在较重的睡眠困扰。请优先减少独自承受的压力，并考虑尽快联系校园支持资源。",
      },
    },
    nextCode: null,
    nextLabel: "",
    homeLabel: "返回首页查看最新进度",
  },
  UPI: {
    code: "UPI",
    name: "UPI 辅助筛查",
    route: PAGE_ROUTES.QUESTIONNAIRE_UPI,
    pageStep: "S09",
    heroEyebrow: "S09 UPI",
    heroTitle: "补充完成 UPI 辅助筛查",
    heroSummary:
      "共 4 题，采用“是 / 否”作答，用于补充识别风险信号。它不会阻塞完整报告解锁，但会影响辅助风险判断。",
    scaleLabel: "是 / 否 题型",
    scoreLabel: "辅助结果",
    unlockRequired: false,
    optionalHint: "这是可选问卷，不影响 70 题完整报告解锁。",
    disclaimer:
      "UPI 仅作辅助风险参考，不参与完整报告总分；如你当下已明显不适，请优先联系可信赖的人或校园支持资源。",
    latestHint:
      "你此前已经完成过一份 UPI。若再次提交，系统会以最新结果作为辅助风险参考。",
    resultCopy: {
      low: {
        title: "当前 UPI 结果已保存",
        summary:
          "这份辅助筛查已成功保存。它不会影响完整报告解锁，但会在后续综合判断中作为补充参考。",
      },
      watch: {
        title: "当前 UPI 结果已保存",
        summary:
          "这份辅助筛查已成功保存。它不会阻塞完整报告解锁，但建议你继续留意近期状态变化。",
      },
      high: {
        title: "当前 UPI 结果提示需要优先关注",
        summary:
          "这份辅助筛查触发了较高风险信号。请优先关注当下安全，尽快联系可信赖的人或校园支持资源。",
      },
    },
    nextCode: null,
    nextLabel: "",
    homeLabel: "返回首页",
  },
};

const QUESTIONNAIRE_ORDER = ["SCREEN", "SDS", "SAS", "SLEEP", "UPI"];

function getQuestionnairePageConfig(code) {
  if (!code) {
    return null;
  }
  return QUESTIONNAIRE_PAGE_CONFIG[String(code).toUpperCase()] || null;
}

function getQuestionnaireRouteByCode(code) {
  const config = getQuestionnairePageConfig(code);
  return config ? config.route : "";
}

module.exports = {
  QUESTIONNAIRE_ORDER,
  QUESTIONNAIRE_PAGE_CONFIG,
  getQuestionnairePageConfig,
  getQuestionnaireRouteByCode,
};
