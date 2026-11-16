/**
 * Cut ranges from the transcript: the source span of a selection of words,
 * cutting it from a clip, restoring a cut, and which words a cut removes.
 */
import type { Word } from "@/api/types";
import { fitCuts, type ClipRange, type CutRange } from "@/lib/timeline";

/** A run of selected words: indices of the first pressed and the last
 * reached word (either may be the larger). */
export interface WordSelection {
  anchor: number;
  focus: number;
}

/** The first and last index of a selection, in order. */
export function selectionBounds(selection: WordSelection): [number, number] {
  const { anchor, focus } = selection;
  return [Math.min(anchor, focus), Math.max(anchor, focus)];
}

/** Whether word index lies in selection. */
export function isSelected(
  selection: WordSelection | null,
  index: number,
): boolean {
  if (!selection) return false;
  const [first, last] = selectionBounds(selection);
  return index >= first && index <= last;
}

/**
 * The source span of the selected words: from the start of the first to
 * the end of the last; null if the selection has no words.
 */
export function selectionSpan(
  words: Word[],
  selection: WordSelection,
): CutRange | null {
  const [first, last] = selectionBounds(selection);
  const from = words[first];
  const to = words[Math.min(last, words.length - 1)];
  if (!from || !to || to.end <= from.start) return null;
  return [from.start, to.end];
}

/** Sort cuts by start and merge those that overlap or touch. */
export function mergeCuts(cuts: CutRange[]): CutRange[] {
  return fitCuts(cuts, { start: -Infinity, end: Infinity });
}

/**
 * The cuts after cutting span from clip: span is trimmed to the clip
 * (nothing changes if none of it is in the clip) and merged with the cuts.
 */
export function addCut(
  cuts: CutRange[],
  span: CutRange,
  clip: ClipRange,
): CutRange[] {
  const [inside] = fitCuts([span], clip);
  return inside ? mergeCuts([...cuts, inside]) : cuts;
}

/**
 * The cuts without the source time that removed covers: each cut keeps
 * the parts of it outside every removed range (turning auto cut off keeps
 * the user's own cuts).
 */
export function subtractCuts(
  cuts: CutRange[],
  removed: CutRange[],
): CutRange[] {
  const gone = mergeCuts(removed);
  return cuts.flatMap(([start, end]) => {
    const kept: CutRange[] = [];
    let from = start;
    for (const [goneStart, goneEnd] of gone) {
      if (goneEnd <= from || goneStart >= end) continue;
      if (goneStart > from) kept.push([from, goneStart]);
      from = Math.max(from, goneEnd);
    }
    if (from < end) kept.push([from, end]);
    return kept;
  });
}

/** The cut that removes source time t, if any. */
export function cutAt(cuts: CutRange[], t: number): CutRange | undefined {
  return cuts.find(([from, to]) => t >= from && t <= to);
}

/** The cuts without the one that removes source time t (restoring it). */
export function restoreCut(cuts: CutRange[], t: number): CutRange[] {
  const cut = cutAt(cuts, t);
  return cut ? cuts.filter((other) => other !== cut) : cuts;
}

/** Whether a cut removes word: one holds the middle of the word. */
export function isCut(word: Word, cuts: CutRange[]): boolean {
  return cutAt(cuts, wordMiddle(word)) !== undefined;
}

/** The source time in the middle of word. */
export function wordMiddle(word: Word): number {
  return (word.start + word.end) / 2;
}

/** Where a word lies relative to a clip: before it, in it or after it (by
 * its start, as the backend puts words in a clip). */
export function wordPlace(
  word: Word,
  clip: ClipRange,
): "before" | "inside" | "after" {
  if (word.start < clip.start) return "before";
  return word.start < clip.end ? "inside" : "after";
}
