import type { Clip, Scores } from "@/api/types";

export type ScoreTone = "high" | "medium" | "low";
export type ClipSort = "score" | "duration";

export interface ClipFilter {
  sort: ClipSort;
  minScore: number;
  query: string;
}

/** The color band of a score: 80 and up high (green), 60-79 medium
 * (yellow), below 60 low (gray). */
export function scoreTone(score: number): ScoreTone {
  if (score >= 80) return "high";
  if (score >= 60) return "medium";
  return "low";
}

/** The text color class of each score tone. */
export const SCORE_TEXT: Record<ScoreTone, string> = {
  high: "text-success",
  medium: "text-warning",
  low: "text-muted-foreground",
};

/** The score parts the breakdown shows, with their labels. */
export const SCORE_PARTS: readonly { key: keyof Scores; label: string }[] = [
  { key: "hook", label: "Hook" },
  { key: "flow", label: "Flow" },
  { key: "value", label: "Value" },
  { key: "trend", label: "Trend" },
];

/** The length of a clip in seconds after its cut ranges are removed. */
export function clipLength(clip: Clip): number {
  const cut = clip.cut_ranges.reduce((sum, [from, to]) => sum + (to - from), 0);
  return Math.max(0, clip.end - clip.start - cut);
}

/** Whether the user changed the clip: it has cuts or reworded captions. */
export function isEdited(clip: Clip): boolean {
  return clip.cut_ranges.length > 0 || clip.caption_overrides.length > 0;
}

function searchable(clip: Clip): string {
  return [clip.title, clip.hook_text, clip.description, ...clip.hashtags]
    .join("\n")
    .toLowerCase();
}

/**
 * The clips to show: those with an overall score of at least minScore whose
 * title, hook, description or hashtags contain the query (ignoring case),
 * best score first or shortest first (ties by id).
 */
export function visibleClips(clips: Clip[], filter: ClipFilter): Clip[] {
  const needle = filter.query.trim().toLowerCase();
  return clips
    .filter((clip) => clip.scores.overall >= filter.minScore)
    .filter((clip) => needle === "" || searchable(clip).includes(needle))
    .sort((a, b) =>
      filter.sort === "duration"
        ? clipLength(a) - clipLength(b) || a.id - b.id
        : b.scores.overall - a.scores.overall || a.id - b.id,
    );
}
