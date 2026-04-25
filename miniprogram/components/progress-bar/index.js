Component({
  properties: {
    current: {
      type: Number,
      value: 0,
    },
    total: {
      type: Number,
      value: 100,
    },
    label: {
      type: String,
      value: "",
    },
  },

  data: {
    percentage: 0,
  },

  observers: {
    "current,total": function updatePercentage(current, total) {
      if (!total || total <= 0) {
        this.setData({ percentage: 0 });
        return;
      }
      const safePercentage = Math.max(0, Math.min(100, (current / total) * 100));
      this.setData({ percentage: safePercentage });
    },
  },
});
