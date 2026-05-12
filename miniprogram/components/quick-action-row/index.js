Component({
  properties: {
    items: {
      type: Array,
      value: [],
    },
  },

  methods: {
    handleActionTap(event) {
      const { key } = event.currentTarget.dataset;
      if (!key) {
        return;
      }
      this.triggerEvent("action", { key });
    },
  },
});
