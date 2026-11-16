import type { ProcessingSettings } from "@/api/types";

type Option<T extends string> = { value: T; label: string };

export type LengthPreset = ProcessingSettings["length_presets"][number];

export const GENRES: Option<ProcessingSettings["genre"]>[] = [
  { value: "auto", label: "Auto" },
  { value: "comedy", label: "Comedy" },
  { value: "sports_commentary", label: "Sports commentary" },
  { value: "faith", label: "Faith / sermon" },
  { value: "news", label: "News" },
  { value: "vlog", label: "Vlog" },
  { value: "gaming", label: "Gaming" },
  { value: "podcast", label: "Podcast" },
  { value: "talk", label: "Talk" },
  { value: "interview", label: "Interview" },
  { value: "other", label: "Other" },
];

export const LENGTHS: Option<LengthPreset>[] = [
  { value: "auto", label: "Auto (0–3m)" },
  { value: "lt30", label: "< 30s" },
  { value: "30_60", label: "30–59s" },
  { value: "60_90", label: "60–89s" },
  { value: "90_180", label: "90s–3m" },
  { value: "180_300", label: "3–5m" },
  { value: "300_600", label: "5–10m" },
  { value: "600_900", label: "10–15m" },
];

export const ASPECTS: Option<ProcessingSettings["aspect"]>[] = [
  { value: "9:16", label: "9:16 vertical" },
  { value: "1:1", label: "1:1 square" },
  { value: "4:5", label: "4:5 portrait" },
  { value: "16:9", label: "16:9 landscape" },
];

export const MIN_CLIPS = 1;
export const MAX_CLIPS = 30;

/**
 * The [start, end] seconds that the timeframe slider shows: an unset start
 * is the start of the video and an unset end its end.
 */
export function timeframeRange(
  settings: ProcessingSettings,
  duration: number,
): [number, number] {
  const start = Math.min(settings.timeframe_start ?? 0, duration);
  const end = Math.min(settings.timeframe_end ?? duration, duration);
  return [start, end];
}

/**
 * The timeframe fields for a slider range: a range that starts at 0 or ends
 * at the end of the video leaves that side unset (the whole video).
 */
export function timeframeFields(
  [start, end]: [number, number],
  duration: number,
): Pick<ProcessingSettings, "timeframe_start" | "timeframe_end"> {
  return {
    timeframe_start: start > 0 ? start : null,
    timeframe_end: end < duration ? end : null,
  };
}

/**
 * The length presets after clicking one: "auto" stands alone, so choosing it
 * clears the others and choosing another range drops it; unchoosing the
 * last range falls back to "auto". Kept in the order of LENGTHS.
 */
export function toggleLength(
  chosen: readonly LengthPreset[],
  value: LengthPreset,
): ProcessingSettings["length_presets"] {
  if (value === "auto") return ["auto"];
  const next = chosen.includes(value)
    ? chosen.filter((preset) => preset !== value)
    : [...chosen.filter((preset) => preset !== "auto"), value];
  const ordered = LENGTHS.map((option) => option.value).filter((preset) =>
    next.includes(preset),
  );
  const [first, ...rest] = ordered;
  return first ? [first, ...rest] : ["auto"];
}

/**
 * Seconds from a typed time: "75", "1:15" or "1:01:15" (fractions of a
 * second allowed). Null when it is not a time.
 */
export function parseTime(text: string): number | null {
  const parts = text.trim().split(":");
  if (parts.length > 3 || parts.some((part) => !/^\d+(\.\d+)?$/.test(part)))
    return null;
  return parts.reduce((total, part) => total * 60 + Number(part), 0);
}

/**
 * The settings to send: the keyword prompt trimmed, or null when empty, and
 * at least one length preset.
 */
export function settingsToSend(
  settings: ProcessingSettings,
): ProcessingSettings {
  const keywords = settings.keyword_prompt?.trim() ?? "";
  const [first, ...rest] = settings.length_presets;
  return {
    ...settings,
    keyword_prompt: keywords || null,
    length_presets: first ? [first, ...rest] : ["auto"],
  };
}

/** "karaoke_bold" -> "Karaoke bold". */
export function templateLabel(name: string): string {
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The default layouts whose clips may zoom out; a layout chosen for every
 * clip is kept as it is. */
export const ZOOMS_OUT: ProcessingSettings["default_layout"][] = [
  "auto",
  "dynamic",
];
