Component({
  properties: {
    label: {
      type: String,
      value: "",
    },
    loading: {
      type: Boolean,
      value: false,
    },
    disabled: {
      type: Boolean,
      value: false,
    },
  },

  methods: {
    handleTap() {
      if (this.properties.loading || this.properties.disabled) {
        return;
      }
      this.triggerEvent("tap");
    },
  },
});
