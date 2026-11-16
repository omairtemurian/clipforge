/**
 * The look of a clip that the Captions and Layout panels and the player
 * toolbar edit: its layout, caption template with the style fields that
 * replace the template's, the texts of its caption words, the shift of its
 * crop, its framing (aspect, fit background, crop tool), whether its
 * silences are cut (auto cut) and its punch-ins (auto zoom).
 */
import type {
  CaptionStyle,
  CaptionTemplate,
  Clip,
  Framing,
  Word,
  ZoomKeyframe,
} from "@/api/types";

export interface ClipLook {
  layout: Clip["layout"];
  caption_template: string;
  caption_style: CaptionStyle;
  caption_overrides: Word[];
  crop_offset: number;
  framing: Framing;
  auto_cut: boolean;
  auto_zoom: boolean;
  zoom_keyframes: ZoomKeyframe[];
}

/** A style that keeps everything of its template. */
export const NO_STYLE: CaptionStyle = {
  size: null,
  primary_color: null,
  highlight_color: null,
  emphasis_color: null,
  position: null,
  uppercase: null,
  emoji: null,
  font: null,
  outline: null,
  outline_color: null,
  shadow: null,
  box: null,
  max_lines: null,
  max_words_per_line: null,
  animation: null,
  speaker_colors: null,
  word_marks: null,
  translation: null,
  censor: null,
};

/** The style fields that belong to the clip, not to a template: they stay
 * when the template changes or the style is reset. */
const CLIP_FIELDS = [
  "speaker_colors",
  "word_marks",
  "translation",
  "censor",
] as const;

/** style without its template fields (all unset), keeping the clip's
 * speaker colors, word marks, caption translation and censor. */
export function resetStyle(style: CaptionStyle): CaptionStyle {
  return {
    ...NO_STYLE,
    speaker_colors: style.speaker_colors,
    word_marks: style.word_marks,
    translation: style.translation,
    censor: style.censor,
  };
}

/** style's template fields only: the clip's own fields unset. */
export function templateFields(style: CaptionStyle): CaptionStyle {
  return {
    ...style,
    speaker_colors: null,
    word_marks: null,
    translation: null,
    censor: null,
  };
}

/** The look of clip as saved. */
export function clipLook(clip: Clip): ClipLook {
  return {
    layout: clip.layout,
    caption_template: clip.caption_template,
    caption_style: clip.caption_style,
    caption_overrides: clip.caption_overrides,
    crop_offset: clip.crop_offset,
    framing: clip.framing,
    auto_cut: clip.auto_cut,
    auto_zoom: clip.auto_zoom,
    zoom_keyframes: clip.zoom_keyframes,
  };
}

/** The style fields the panel edits: template fields that style can replace. */
export type StyleField = Exclude<
  keyof CaptionStyle,
  (typeof CLIP_FIELDS)[number]
>;

/** The caption template as drawn: its fields, with those that style sets
 * replaced. */
export function effectiveTemplate(
  template: CaptionTemplate,
  style: CaptionStyle,
): CaptionTemplate {
  const set = Object.fromEntries(
    Object.entries(style).filter(
      ([field, value]) =>
        value !== null && !(CLIP_FIELDS as readonly string[]).includes(field),
    ),
  );
  return { ...template, ...set };
}

function sameValue(a: string | number | boolean, b: string | number | boolean) {
  return typeof a === "string" && typeof b === "string"
    ? a.toLowerCase() === b.toLowerCase()
    : a === b;
}

/** style with field set to value; a value equal to the template's is kept
 * as the template's (null), so that an unchanged field stays unset. */
export function withStyleField<F extends StyleField>(
  style: CaptionStyle,
  template: CaptionTemplate,
  field: F,
  value: NonNullable<CaptionStyle[F]>,
): CaptionStyle {
  const same = sameValue(value, template[field]);
  return { ...style, [field]: same ? null : value };
}

/** Whether style replaces any field of its template (speaker colors and word
 * marks do not count). */
export function isStyled(style: CaptionStyle): boolean {
  return Object.entries(style).some(
    ([field, value]) =>
      value !== null && !(CLIP_FIELDS as readonly string[]).includes(field),
  );
}
