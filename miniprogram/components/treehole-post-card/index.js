Component({
  properties: {
    anonymousName: {
      type: String,
      value: "",
    },
    relativeTime: {
      type: String,
      value: "",
    },
    content: {
      type: String,
      value: "",
    },
    anonymousAvatarKey: {
      type: String,
      value: "",
    },
    fullContent: {
      type: Boolean,
      value: false,
    },
  },

  data: {
    avatarText: "匿",
    avatarToneClass: "treehole-post-card__avatar--brand",
  },

  observers: {
    "anonymousName, anonymousAvatarKey": function (anonymousName, anonymousAvatarKey) {
      const sourceText = String(anonymousName || "").trim();
      const avatarText = sourceText ? sourceText.slice(0, 1) : "匿";
      const sourceKey = String(anonymousAvatarKey || anonymousName || "");
      let hash = 0;
      for (let index = 0; index < sourceKey.length; index += 1) {
        hash = (hash + sourceKey.charCodeAt(index) * (index + 3)) % 4;
      }

      const toneClasses = [
        "treehole-post-card__avatar--brand",
        "treehole-post-card__avatar--warm",
        "treehole-post-card__avatar--deep",
        "treehole-post-card__avatar--mist",
      ];
      this.setData({
        avatarText,
        avatarToneClass: toneClasses[hash],
      });
    },
  },
});
