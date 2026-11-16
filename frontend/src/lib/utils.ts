import { createCn } from "cn/config";

/**
 * Join class names and resolve Tailwind conflicts; knows the app's own
 * type scale (text-display/title/section/body/caption/micro, see index.css) and
 * named spacing (page, section), so they are not taken for colors.
 */
export const cn = createCn({
  extend: {
    theme: {
      spacing: ["page", "section"],
      container: ["form", "wide"],
      shadow: ["card", "card-hover", "popover"],
    },
    classGroups: {
      "font-size": [
        {
          text: ["display", "title", "section", "body", "caption", "micro"],
        },
      ],
    },
  },
});
