import { describe, expect, it } from "vitest";
import type { CaptionTemplate } from "@/api/types";
import { clip } from "@/testing/mockApi";
import { DEFAULT_FRAMING } from "./cropFrame";
import {
  NO_STYLE,
  clipLook,
  effectiveTemplate,
  isStyled,
  resetStyle,
  withStyleField,
} from "./clipLook";

const TEMPLATE: CaptionTemplate = {
  font: "Montserrat ExtraBold",
  size: 80,
  primary_color: "#FFFFFF",
  highlight_color: "#FF6B35",
  emphasis_color: "#FFD23F",
  outline: 14,
  shadow: 0,
  box: true,
  uppercase: true,
  position: "middle",
  max_words_per_line: 3,
  outline_color: "#000000",
  max_lines: 1,
  animation: "none",
  emoji: false,
};

describe("clipLook", () => {
  it("takes the look fields of a clip", () => {
    const zoom = [
      { t: 1, scale: 1 },
      { t: 1.2, scale: 1.15 },
    ];
    const saved = clip({
      layout: "split",
      crop_offset: 0.2,
      auto_cut: true,
      auto_zoom: true,
      zoom_keyframes: zoom,
    });

    expect(clipLook(saved)).toEqual({
      layout: "split",
      caption_template: "karaoke_bold",
      caption_style: NO_STYLE,
      caption_overrides: [],
      crop_offset: 0.2,
      framing: DEFAULT_FRAMING,
      auto_cut: true,
      auto_zoom: true,
      zoom_keyframes: zoom,
    });
  });
});

describe("effectiveTemplate", () => {
  it("keeps the template when nothing is set", () => {
    expect(effectiveTemplate(TEMPLATE, NO_STYLE)).toEqual(TEMPLATE);
  });

  it("replaces only the fields the style sets, also falsy ones", () => {
    const shown = effectiveTemplate(TEMPLATE, {
      ...NO_STYLE,
      size: 64,
      uppercase: false,
    });

    expect(shown).toEqual({ ...TEMPLATE, size: 64, uppercase: false });
  });
});

describe("withStyleField", () => {
  it("sets a field that differs from the template", () => {
    const style = withStyleField(NO_STYLE, TEMPLATE, "size", 96);

    expect(style).toEqual({ ...NO_STYLE, size: 96 });
    expect(isStyled(style)).toBe(true);
  });

  it("unsets a field that is back to the template's value", () => {
    const style = withStyleField(
      { ...NO_STYLE, primary_color: "#112233", emoji: true },
      TEMPLATE,
      "primary_color",
      "#ffffff",
    );

    expect(style).toEqual({ ...NO_STYLE, emoji: true });
  });

  it("sets a boolean that differs, also false", () => {
    expect(withStyleField(NO_STYLE, TEMPLATE, "uppercase", false)).toEqual({
      ...NO_STYLE,
      uppercase: false,
    });
    expect(isStyled(NO_STYLE)).toBe(false);
  });
});

describe("speaker colors, word marks, translation and censor", () => {
  const clipFields = {
    speaker_colors: { S0: "#00FF00" },
    word_marks: [
      {
        start: 1.5,
        emphasis: true,
        emoji: "🔥",
        censor: true,
        color: null,
        source: "ai" as const,
      },
    ],
    translation: {
      language: "fa",
      cues: [{ start: 1.5, end: 2.4, text: "سلام دنیا", speaker: "S0" }],
    },
    censor: { auto: true, mode: "mute" as const },
  };

  it("are not template fields: they do not style or change the template", () => {
    const style = { ...NO_STYLE, ...clipFields };

    expect(isStyled(style)).toBe(false);
    expect(effectiveTemplate(TEMPLATE, style)).toEqual(TEMPLATE);
  });

  it("stay when the style is reset", () => {
    const style = { ...NO_STYLE, ...clipFields, size: 96 };

    expect(resetStyle(style)).toEqual({ ...NO_STYLE, ...clipFields });
  });
});
