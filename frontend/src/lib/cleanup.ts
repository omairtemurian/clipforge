/**
 * Speech cleanup: which of the filler and pause cuts the backend suggests
 * (GET /clips/{id}/cleanup-suggestions) the editor applies.
 */
import type { CleanupSuggestion } from "@/api/types";
import { cutAt } from "@/lib/cuts";
import type { CutRange } from "@/lib/timeline";

/** Whether the clip's cuts already remove suggestion whole. */
export function isApplied(
  suggestion: CleanupSuggestion,
  cuts: CutRange[],
): boolean {
  const cut = cutAt(cuts, suggestion.start);
  return cut !== undefined && cut[1] >= suggestion.end;
}

/**
 * The cut ranges of the suggestions to apply: those not left unchecked
 * (indices in unchecked) nor already cut, in order.
 */
export function cleanupCuts(
  suggestions: CleanupSuggestion[],
  unchecked: ReadonlySet<number>,
  cuts: CutRange[],
): CutRange[] {
  return suggestions
    .filter((s, index) => !unchecked.has(index) && !isApplied(s, cuts))
    .map((s): CutRange => [s.start, s.end]);
}

/** How a suggestion reads in the review list: the filler words in quotes,
 * a bad take as its words, or "Pause". */
export function suggestionLabel(suggestion: CleanupSuggestion): string {
  if (suggestion.kind === "filler") return `“${suggestion.text}”`;
  return suggestion.kind === "bad_take" ? suggestion.text : "Pause";
}

/** The pause threshold of speech cleanup in seconds: its default, least and
 * most (the backend's CLEANUP_PAUSE_S, CLEANUP_PAUSE_MIN_S and
 * CLEANUP_PAUSE_MAX_S). */
export const PAUSE_DEFAULT_S = 0.6;
export const PAUSE_MIN_S = 0.3;
export const PAUSE_MAX_S = 10;

/** The strength of speech enhancement as a percentage. */
export function strengthLabel(strength: number): string {
  return strength === 0 ? "Off" : `${Math.round(strength * 100)}%`;
}
