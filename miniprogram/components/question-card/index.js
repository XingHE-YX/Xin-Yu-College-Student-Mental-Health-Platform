Component({
  options: {
    multipleSlots: true,
  },

  properties: {
    questionNumber: {
      type: String,
      value: "",
    },
    title: {
      type: String,
      value: "",
    },
    description: {
      type: String,
      value: "",
    },
  },
});
