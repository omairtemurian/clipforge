/** How the editor's version history names a clip's versions. */
import type { ClipVersionInfo } from "@/api/types";

/** The clip fields (ClipState) in the user's words. */
const FIELD_LABELS: Record<string, string> = {
  segments: "trim",
  cut_ranges: "cuts",
  tracks: "tracks",
  title: "title",
  hook_text: "hook",
  description: "description",
  hashtags: "hashtags",
  emphasis_words: "emphasis",
  layout: "layout",
  caption_template: "captions",
  caption_overrides: "captions",
  caption_style: "captions",
  show_captions: "captions",
  crop_offset: "crop",
  framing: "crop",
  scene_reframes: "scenes",
  auto_cut: "auto cut",
  auto_zoom: "zoom",
  zoom_keyframes: "zoom",
  auto_color: "color",
  enhance: "enhancement",
};

/** The most changed fields a version names before "+N more". */
const SHOWN_FIELDS = 3;

/** What changed in fields, in words: "trim, cuts, +2 more". */
export function fieldsLabel(fields: string[]): string {
  const words = [
    ...new Set(fields.map((f) => FIELD_LABELS[f] ?? f.replace(/_/g, " "))),
  ];
  const shown = words.slice(0, SHOWN_FIELDS).join(", ");
  const more = words.length - SHOWN_FIELDS;
  return more > 0 ? `${shown}, +${more} more` : shown;
}

/** What a version did: "Original clip", "Restored version 3", "Edited
 * trim, cuts". */
export function versionSummary(version: ClipVersionInfo): string {
  if (version.kind === "original") return "Original clip";
  if (version.kind === "restore") {
    return `Restored version ${version.restored_from ?? "?"}`;
  }
  return version.fields.length > 0
    ? `Edited ${fieldsLabel(version.fields)}`
    : "Edited";
}
