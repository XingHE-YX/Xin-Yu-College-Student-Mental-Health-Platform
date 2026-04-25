Component({
  properties: {
    visible: {
      type: Boolean,
      value: false,
    },
    title: {
      type: String,
      value: "",
    },
    message: {
      type: String,
      value: "",
    },
    confirmText: {
      type: String,
      value: "确认",
    },
    cancelText: {
      type: String,
      value: "取消",
    },
    tone: {
      type: String,
      value: "danger",
    },
  },

  methods: {
    handleMaskTap() {
      this.triggerEvent("cancel");
    },

    handleCancel() {
      this.triggerEvent("cancel");
    },

    handleConfirm() {
      this.triggerEvent("confirm");
    },
  },
});
