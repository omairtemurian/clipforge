/**
 * The caption colors of a processing preset: the words and the spoken word's
 * colors that replace those of the chosen caption template, whichever it is.
 */
import type { CaptionTemplate, ProcessingSettings } from "@/api/types";

export type CaptionColors = ProcessingSettings["caption_colors"];
export type CaptionColorField = keyof CaptionColors;

/** Colors that keep everything of the template. */
export const NO_COLORS: CaptionColors = {
  primary_color: null,
  highlight_color: null,
  emphasis_color: null,
};

/** Ready-made pairs: the words in white and the spoken word in a color. */
export const COLOR_PAIRS = [
  { label: "White + green", text: "#FFFFFF", spoken: "#22C55E" },
  { label: "White + yellow", text: "#FFFFFF", spoken: "#FFD60A" },
  { label: "White + orange", text: "#FFFFFF", spoken: "#FF6B35" },
] as const;

/** The color a field shows: the preset's, else the template's. */
export function shownColor(
  template: CaptionTemplate,
  colors: CaptionColors,
  field: CaptionColorField,
): string {
  return colors[field] ?? template[field];
}

/** colors with field set to color; the template's own color is kept as unset
 * (null), so that choosing another template brings its colors. */
export function withColor(
  colors: CaptionColors,
  template: CaptionTemplate,
  field: CaptionColorField,
  color: string,
): CaptionColors {
  const same = color.toLowerCase() === template[field].toLowerCase();
  return { ...colors, [field]: same ? null : color };
}

/** Whether colors replace any color of the template. */
export function hasColors(colors: CaptionColors): boolean {
  return Object.values(colors).some((color) => color !== null);
}
