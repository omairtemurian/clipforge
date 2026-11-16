/**
 * The clip's segments on the timeline: split points cut the clip into
 * parts, cut ranges leave gaps, and a time can snap to a word's edge.
 */
import type { Word } from "@/api/types";
import { mergeCuts } from "@/lib/cuts";
import { snapTime } from "@/lib/snap";
import { MIN_CLIP_S, type ClipRange, type CutRange } from "@/lib/timeline";

/** The shortest part a split leaves on either side, in seconds. */
export const MIN_SEGMENT_S = 0.1;
/** How far (seconds) a split looks for a word's edge to snap to. */
export const SNAP_SPLIT_S = 0.5;

/**
 * The split points after splitting at source time t: t must lie inside the
 * clip, at least MIN_SEGMENT_S from its ends and from the other splits,
 * else nothing changes. Sorted.
 */
export function addSplit(
  splits: number[],
  t: number,
  clip: ClipRange,
): number[] {
  const edges = [clip.start, clip.end, ...splits];
  if (t <= clip.start || t >= clip.end) return splits;
  if (edges.some((edge) => Math.abs(edge - t) < MIN_SEGMENT_S)) return splits;
  return [...splits, Number(t.toFixed(3))].sort((a, b) => a - b);
}

/**
 * The parts of the clip that are kept, in order: the clip split at its
 * split points, with the cut ranges taken out.
 */
export function segments(
  clip: ClipRange,
  splits: number[],
  cuts: CutRange[],
): CutRange[] {
  const inside = splits.filter((t) => t > clip.start && t < clip.end);
  const points = [clip.start, ...inside, clip.end];
  const pieces: CutRange[] = [];
  for (let index = 1; index < points.length; index += 1) {
    let from = points[index - 1];
    const to = points[index];
    for (const [cutFrom, cutTo] of mergeCuts(cuts)) {
      if (cutTo <= from || cutFrom >= to) continue;
      if (cutFrom > from) pieces.push([from, cutFrom]);
      from = Math.max(from, cutTo);
    }
    if (to > from) pieces.push([from, to]);
  }
  return pieces.filter(([from, to]) => to - from > 1e-6);
}

/** The segment that holds source time t, if any. */
export function segmentAt(parts: CutRange[], t: number): CutRange | undefined {
  return parts.find(([from, to]) => t >= from && t < to);
}

/** Whether cutting part out of the clip leaves at least MIN_CLIP_S. */
export function canCutSegment(parts: CutRange[], part: CutRange): boolean {
  const kept = parts.reduce((sum, [from, to]) => sum + to - from, 0);
  return kept - (part[1] - part[0]) >= MIN_CLIP_S - 1e-9;
}

/**
 * Source time t moved to the nearest start or end of a word within
 * tolerance seconds; t itself if no word edge is that close.
 */
export function snapToWords(
  t: number,
  words: Word[],
  tolerance: number,
): number {
  return snapTime(t, wordEdges(words), tolerance);
}

/** The starts and ends of words, in order. */
export function wordEdges(words: Word[]): number[] {
  return words.flatMap((word) => [word.start, word.end]);
}

/**
 * The nearest of points before t (direction -1) or after it (+1), skipping
 * those within MIN_SEGMENT_S of t; undefined if there is none.
 */
export function adjacentPoint(
  points: number[],
  t: number,
  direction: -1 | 1,
): number | undefined {
  const sorted = [...points].sort((a, b) => a - b);
  if (direction < 0) {
    return sorted.reverse().find((point) => point < t - MIN_SEGMENT_S);
  }
  return sorted.find((point) => point > t + MIN_SEGMENT_S);
}
