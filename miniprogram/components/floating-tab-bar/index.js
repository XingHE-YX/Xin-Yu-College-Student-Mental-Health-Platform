const { getPrimaryTabItems } = require("../../constants/navigation");

Component({
  properties: {
    activeKey: {
      type: String,
      value: "assessment",
    },
  },

  data: {
    items: getPrimaryTabItems(),
  },

  methods: {
    handleItemTap(event) {
      const { key } = event.currentTarget.dataset;
      if (!key || key === this.properties.activeKey) {
        return;
      }
      this.triggerEvent("change", { key });
    },
  },
});
