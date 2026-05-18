Component({
  properties: {
    label: {
      type: String,
      value: "",
    },
    count: {
      type: Number,
      value: 0,
    },
    active: {
      type: Boolean,
      value: false,
    },
    busy: {
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
      if (this.properties.disabled) {
        return;
      }
      this.triggerEvent("tap");
    },
  },
});
