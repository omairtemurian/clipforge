/**
 * Pure math of the editor timeline: source seconds <-> pixels, the window of
 * the source it shows, moving the clip's start/end handles, and the mapping
 * between the preview's time (cut ranges removed) and the source's time.
 */

export type CutRange = [number, number];

/** A clip's span on the source video, in seconds. */
export interface ClipRange {
  start: number;
  end: number;
}

/** The part of the source a timeline shows (seconds) and its width (px). */
export interface TimelineView {
  from: number;
  to: number;
  width: number;
}

export type Handle = "start" | "end";

/** Seconds of source the timeline shows before and after the clip. */
export const CONTEXT_S = 30;
/** The shortest clip the handles can make, in seconds. */
export const MIN_CLIP_S = 1;

const TICK_STEPS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];

/** Clamp value into [low, high]. */
export function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/**
 * The window of the source around a clip: CONTEXT_S seconds before its start
 * and after its end, inside the video (duration 0 = not known: no upper end).
 */
export function contextWindow(
  clip: ClipRange,
  duration: number,
  context = CONTEXT_S,
): ClipRange {
  const end = clip.end + context;
  return {
    start: Math.max(0, clip.start - context),
    end: duration > 0 ? Math.max(clip.end, Math.min(duration, end)) : end,
  };
}

/** The x position (px from the left edge) of source time t in view. */
export function timeToPx(t: number, view: TimelineView): number {
  const span = view.to - view.from;
  if (span <= 0 || view.width <= 0) return 0;
  return ((t - view.from) / span) * view.width;
}

/** The source time at x px from the left edge of view, inside the view. */
export function pxToTime(px: number, view: TimelineView): number {
  if (view.width <= 0) return view.from;
  const t = view.from + (px / view.width) * (view.to - view.from);
  return clamp(t, view.from, view.to);
}

/** The left edge and width of [start, end] within view, as percentages. */
export function spanPercent(
  start: number,
  end: number,
  view: ClipRange,
): { left: number; width: number } {
  const percent = { from: view.start, to: view.end, width: 100 };
  const left = clamp(timeToPx(start, percent), 0, 100);
  const right = clamp(timeToPx(end, percent), 0, 100);
  return { left, width: Math.max(0, right - left) };
}

/**
 * The clip after dragging one of its handles to source time t: the handle
 * stays inside bounds and at least minLength seconds from the other one,
 * which does not move.
 */
export function moveHandle(
  clip: ClipRange,
  handle: Handle,
  t: number,
  bounds: ClipRange,
  minLength = MIN_CLIP_S,
): ClipRange {
  if (handle === "start") {
    const latest = Math.max(bounds.start, clip.end - minLength);
    return { start: clamp(t, bounds.start, latest), end: clip.end };
  }
  const earliest = Math.min(bounds.end, clip.start + minLength);
  return { start: clip.start, end: clamp(t, earliest, bounds.end) };
}

/**
 * The cut ranges that remain inside a clip from start to end: each is
 * trimmed to the clip, those left empty are dropped and overlapping ones
 * merged, sorted by start.
 */
export function fitCuts(cuts: CutRange[], clip: ClipRange): CutRange[] {
  const inside = cuts
    .map(([from, to]): CutRange => [
      Math.max(from, clip.start),
      Math.min(to, clip.end),
    ])
    .filter(([from, to]) => to > from)
    .sort((a, b) => a[0] - b[0]);
  const merged: CutRange[] = [];
  for (const [from, to] of inside) {
    const last = merged[merged.length - 1];
    if (last && from <= last[1]) last[1] = Math.max(last[1], to);
    else merged.push([from, to]);
  }
  return merged;
}

/** The source time shown at time t of a clip's preview (cuts removed). */
export function previewToSource(
  t: number,
  clip: ClipRange,
  cuts: CutRange[],
): number {
  let source = clip.start + Math.max(0, t);
  for (const [from, to] of fitCuts(cuts, clip)) {
    if (source < from) break;
    source += to - from;
  }
  return Math.min(source, clip.end);
}

/**
 * The time of a clip's preview that shows source time t; a time inside a
 * cut range maps to the end of the cut, one outside the clip to its edge.
 */
export function sourceToPreview(
  t: number,
  clip: ClipRange,
  cuts: CutRange[],
): number {
  const source = clamp(t, clip.start, clip.end);
  let removed = 0;
  for (const [from, to] of fitCuts(cuts, clip)) {
    if (source <= from) break;
    removed += Math.min(source, to) - from;
  }
  return source - clip.start - removed;
}

/**
 * The ruler's step in seconds: the smallest of a set of round steps whose
 * labels are at least minGapPx apart when span seconds fill widthPx.
 */
export function tickStep(span: number, widthPx: number, minGapPx = 64): number {
  if (span <= 0 || widthPx <= 0) return TICK_STEPS[TICK_STEPS.length - 1];
  const perSecond = widthPx / span;
  return (
    TICK_STEPS.find((step) => step * perSecond >= minGapPx) ??
    TICK_STEPS[TICK_STEPS.length - 1]
  );
}

/** The multiples of step from `from` to `to` (inclusive). */
export function ticks(from: number, to: number, step: number): number[] {
  const result: number[] = [];
  const first = Math.ceil(from / step - 1e-9);
  for (let index = first; index * step <= to + 1e-9; index += 1) {
    result.push(Number((index * step).toFixed(3)));
  }
  return result;
}

/** One frame of the preview (rendered at 30 fps), in seconds. */
export const FRAME_S = 1 / 30;
/** The timeline's zoom: how many times the view's width it is drawn. */
export const ZOOM_MIN = 1;
export const ZOOM_MAX = 10;
/** One zoom step (+/- keys and buttons) multiplies or divides by this. */
export const ZOOM_FACTOR = 1.5;

/** The zoom after steps zoom steps in (positive) or out (negative). */
export function zoomBy(zoom: number, steps: number): number {
  const next = zoom * ZOOM_FACTOR ** steps;
  return Number(clamp(next, ZOOM_MIN, ZOOM_MAX).toFixed(3));
}

/** What zoomScroll needs: the anchor's place in the view (0-1), the
 * visible width (px), and the scroll offset and zoom before and after. */
export interface ZoomChange {
  anchor: number;
  viewport: number;
  scroll: number;
  from: number;
  to: number;
}

/**
 * The scroll offset (px) after zooming from `from` to `to` that keeps the
 * anchor (the playhead) where it was on screen, or centers it if it was
 * out of sight; always inside the zoomed content.
 */
export function zoomScroll({
  anchor,
  viewport,
  scroll,
  from,
  to,
}: ZoomChange): number {
  const onScreen = anchor * viewport * from - scroll;
  const keep = onScreen >= 0 && onScreen <= viewport ? onScreen : viewport / 2;
  const next = anchor * viewport * to - keep;
  return clamp(next, 0, Math.max(0, viewport * to - viewport));
}
