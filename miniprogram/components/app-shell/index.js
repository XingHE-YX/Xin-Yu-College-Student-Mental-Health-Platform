Component({
  options: {
    multipleSlots: true,
  },

  properties: {
    padded: {
      type: Boolean,
      value: true,
    },
    withTabBarSpacing: {
      type: Boolean,
      value: false,
    },
  },
});
