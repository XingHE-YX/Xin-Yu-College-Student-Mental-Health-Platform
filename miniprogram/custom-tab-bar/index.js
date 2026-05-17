const { getPrimaryTabItems } = require("../constants/navigation");

Component({
  lifetimes: {
    attached() {
      const page = getCurrentPages().slice(-1)[0];
      if (!page || !page.route) {
        return;
      }
      this.setActiveByRoute(`/${page.route}`);
    },
  },

  data: {
    items: getPrimaryTabItems(),
    activeKey: "assessment",
  },

  methods: {
    handleItemTap(event) {
      const { key, route } = event.currentTarget.dataset;
      if (!key || !route || key === this.data.activeKey) {
        return;
      }

      wx.switchTab({ url: route });
    },

    setActiveByRoute(route) {
      const nextItem = this.data.items.find((item) => item.route === route);
      if (!nextItem || nextItem.key === this.data.activeKey) {
        return;
      }

      this.setData({
        activeKey: nextItem.key,
      });
    },
  },
});
