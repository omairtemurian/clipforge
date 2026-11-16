/**
 * Snap math of the editor timeline: the times a dragged edge snaps to
 * (word edges, segment edges, the playhead, the edges of the items on the
 * other layers) and moving an edge or a whole span onto the nearest of them
 * within a tolerance. All times share one clock (seconds).
 */

/** A span of time, in seconds. */
export interface Span {
  start: number;
  end: number;
}

/** What a dragged item snaps to, each a list of times (seconds). */
export interface SnapSources {
  /** The starts and ends of the transcript's words. */
  words: number[];
  /** The edges of the clip's segments (and the clip's own ends). */
  segments: number[];
  /** Where the playhead is (undefined: nowhere to snap to). */
  playhead?: number;
  /** The edges of the items on the timeline's layers. */
  layers: number[];
}

/**
 * The times of sources to snap to, sorted, each once (snapping off: none).
 */
export function snapTargets(sources: SnapSources, enabled = true): number[] {
  if (!enabled) return [];
  const { words, segments, playhead, layers } = sources;
  const all = [...words, ...segments, ...layers];
  if (playhead !== undefined) all.push(playhead);
  return [...new Set(all.filter(Number.isFinite))].sort((a, b) => a - b);
}

/**
 * The target nearest to t that is at most tolerance seconds away; null if
 * there is none (the earlier one wins a tie).
 */
export function nearestTarget(
  t: number,
  targets: number[],
  tolerance: number,
): number | null {
  if (!(tolerance > 0)) return null;
  let best: number | null = null;
  let distance = tolerance;
  for (const target of targets) {
    const gap = Math.abs(target - t);
    if (gap < distance || (gap === distance && best === null)) {
      best = target;
      distance = gap;
    }
  }
  return best;
}

/** t moved onto the nearest target within tolerance; t if none is. */
export function snapTime(
  t: number,
  targets: number[],
  tolerance: number,
): number {
  return nearestTarget(t, targets, tolerance) ?? t;
}

/**
 * span shifted (its length kept) so that whichever of its edges is nearer
 * a target within tolerance lands on that target; span as it is if neither
 * edge is near one.
 */
export function snapSpan(
  span: Span,
  targets: number[],
  tolerance: number,
): Span {
  const atStart = nearestTarget(span.start, targets, tolerance);
  const atEnd = nearestTarget(span.end, targets, tolerance);
  const shiftStart = atStart === null ? null : atStart - span.start;
  const shiftEnd = atEnd === null ? null : atEnd - span.end;
  const shift =
    shiftStart !== null && shiftEnd !== null
      ? Math.abs(shiftEnd) < Math.abs(shiftStart)
        ? shiftEnd
        : shiftStart
      : (shiftStart ?? shiftEnd ?? 0);
  return { start: span.start + shift, end: span.end + shift };
}
