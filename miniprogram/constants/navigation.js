const { PAGE_ROUTES } = require("./config");

const PRIMARY_CHANNELS = [
  {
    key: "treehole",
    label: "树洞",
    icon: "树",
    route: PAGE_ROUTES.TREEHOLE_FEED,
  },
  {
    key: "assessment",
    label: "测评",
    icon: "测",
    route: PAGE_ROUTES.HOME,
  },
  {
    key: "report",
    label: "报告",
    icon: "报",
    route: PAGE_ROUTES.REPORT_SUMMARY,
  },
  {
    key: "my",
    label: "我的",
    icon: "我",
    route: PAGE_ROUTES.PROFILE,
  },
];

function getPrimaryTabItems() {
  return PRIMARY_CHANNELS.map((item) => ({ ...item }));
}

function getPrimaryChannelRoute(key) {
  const target = PRIMARY_CHANNELS.find((item) => item.key === key);
  return target ? target.route : "";
}

module.exports = {
  PRIMARY_CHANNELS,
  getPrimaryChannelRoute,
  getPrimaryTabItems,
};
