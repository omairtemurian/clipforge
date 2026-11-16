/**
 * Pure math of the Pro Edit editor's EDL lanes (SPEC-v3 3.1, 3.8): which
 * lane an item's kind lies on, the rows of the items that overlap within a
 * lane, what a dragged item snaps to, and the span of an item after a drag
 * or a nudge, kept on the clip's frame grid. Times are seconds of the
 * rendered clip, as in the plan.
 */
import type { EdlItem, ProEditTiming } from "@/api/types";
import { dragSpan, type ItemDrag } from "@/lib/layers";
import { nearestTarget, type Span } from "@/lib/snap";
import { clamp } from "@/lib/timeline";

export type EdlKind = EdlItem["kind"];

/** A lane of the editor: one track of the plan (proedit/edl.py). */
export interface Lane {
  id: string;
  label: string;
  kinds: EdlKind[];
}

/** The lanes, top to bottom: every track of the plan. */
export const LANES: Lane[] = [
  {
    id: "zoom",
    label: "Zoom",
    kinds: ["zoom_punch", "zoom_push", "zoom_out_reveal", "pan"],
  },
  {
    id: "fx",
    label: "FX",
    kinds: [
      "shake",
      "flash",
      "glitch",
      "rgb_split",
      "freeze_frame",
      "speed_ramp",
      "slowmo",
      "transition",
    ],
  },
  { id: "grade", label: "Grade", kinds: ["grade_change", "vignette", "grain"] },
  {
    id: "overlay",
    label: "Overlays",
    kinds: ["overlay", "text_pop", "emoji_pop"],
  },
  { id: "captions", label: "Captions", kinds: ["caption_style"] },
  { id: "sfx", label: "SFX", kinds: ["sfx"] },
  { id: "music", label: "Music", kinds: ["music_bed", "silence_before_drop"] },
  { id: "audio_fx", label: "Audio FX", kinds: ["audio_fx"] },
];

/** The name of each kind as the lanes show it. */
export const KIND_LABELS: Record<EdlKind, string> = {
  zoom_punch: "Zoom punch",
  zoom_push: "Zoom push",
  zoom_out_reveal: "Zoom out",
  pan: "Pan",
  shake: "Shake",
  flash: "Flash",
  glitch: "Glitch",
  rgb_split: "RGB split",
  freeze_frame: "Freeze",
  speed_ramp: "Speed ramp",
  slowmo: "Slow-mo",
  transition: "Transition",
  grade_change: "Grade",
  vignette: "Vignette",
  grain: "Grain",
  overlay: "Overlay",
  text_pop: "Text pop",
  emoji_pop: "Emoji pop",
  caption_style: "Captions",
  sfx: "SFX",
  music_bed: "Music bed",
  silence_before_drop: "Silence",
  audio_fx: "Audio FX",
};

/** The items of lane, in time order. */
export function laneItems(items: EdlItem[], lane: Lane): EdlItem[] {
  return items
    .filter((item) => lane.kinds.includes(item.kind))
    .sort((a, b) => a.t_start - b.t_start || a.id - b.id);
}

/**
 * The row of each item of one lane (by id), from 0: an item goes on the
 * first row whose last item ended by its start (touching items share a
 * row), so overlapping items (stacked SFX and pops) lie on rows of their
 * own.
 */
export function laneRows(items: EdlItem[]): Map<number, number> {
  const ends: number[] = [];
  const rows = new Map<number, number>();
  const sorted = [...items].sort(
    (a, b) => a.t_start - b.t_start || a.id - b.id,
  );
  for (const item of sorted) {
    let row = ends.findIndex((end) => end <= item.t_start + 1e-9);
    if (row === -1) row = ends.length;
    ends[row] = item.t_end;
    rows.set(item.id, row);
  }
  return rows;
}

/** What a dragged edge snapped to (the guide of the snapping preview). */
export type SnapKind = "word" | "beat" | "item" | "playhead";

export interface SnapTarget {
  t: number;
  kind: SnapKind;
  /** The word's text, for a word. */
  text?: string;
}

/**
 * The targets an item snaps to: the word starts and beats of timing, the
 * edges of the other items (not item except) and the playhead, sorted by
 * time; at one time the first kind of that list wins.
 */
export function snapTargets(
  timing: ProEditTiming,
  items: EdlItem[],
  except: number,
  playhead?: number,
): SnapTarget[] {
  const all: SnapTarget[] = [
    ...timing.words.map((w) => ({
      t: w.start,
      kind: "word" as const,
      text: w.text,
    })),
    ...timing.beats.map((t) => ({ t, kind: "beat" as const })),
    ...items
      .filter((item) => item.id !== except)
      .flatMap((item) => [item.t_start, item.t_end])
      .map((t) => ({ t, kind: "item" as const })),
  ];
  if (playhead !== undefined) all.push({ t: playhead, kind: "playhead" });
  const seen = new Set<number>();
  return all
    .filter((target) => {
      const key = Math.round(target.t * 1000);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => a.t - b.t);
}

/** t on the clip's frame grid (round(t * fps) / fps, as the server's
 * snapping does). */
export function frameTime(t: number, fps: number): number {
  return Math.round(t * fps) / fps;
}

/** A drag of an item: what it does, the clip time under the pointer, how
 * far after the item's start it was grabbed, what it snaps to and within
 * how many seconds. */
export interface EdlDragInput {
  drag: ItemDrag;
  pointer: number;
  grab: number;
  targets: SnapTarget[];
  tolerance: number;
}

/** An item's span after a drag, and the target it snapped to (null: none;
 * the snapping preview's guide). */
export interface EdlDrag extends Span {
  guide: SnapTarget | null;
}

/** The target at t (within a millisecond); null if none is. */
function targetAt(t: number, targets: SnapTarget[]): SnapTarget | null {
  const at = nearestTarget(
    t,
    targets.map((target) => target.t),
    0.0011,
  );
  return at === null ? null : (targets.find((x) => x.t === at) ?? null);
}

/**
 * The span of item after a drag (lib/layers dragSpan: moved by its grab or
 * one edge moved to the pointer, the nearer edge snapped to a target
 * within tolerance), then put on the frame grid of timing inside the clip:
 * a move keeps the item's length in frames, a trim keeps it at least one
 * frame long.
 */
export function dragEdlItem(
  item: EdlItem,
  input: EdlDragInput,
  timing: ProEditTiming,
): EdlDrag {
  const { drag, targets } = input;
  const span = dragSpan(
    { start: item.t_start, end: item.t_end },
    { ...input, targets: targets.map((x) => x.t), length: timing.duration },
  );
  const guide =
    drag === "end"
      ? targetAt(span.end, targets)
      : drag === "start"
        ? targetAt(span.start, targets)
        : (targetAt(span.start, targets) ?? targetAt(span.end, targets));
  return { ...onFrames(item, span, drag, timing), guide };
}

/** item moved by seconds (keyboard nudge), on the frame grid. */
export function nudgeEdlItem(
  item: EdlItem,
  seconds: number,
  timing: ProEditTiming,
): Span {
  const span = { start: item.t_start + seconds, end: item.t_end + seconds };
  return onFrames(item, span, "move", timing);
}

function onFrames(
  item: EdlItem,
  span: Span,
  drag: ItemDrag,
  timing: ProEditTiming,
): Span {
  const { fps } = timing;
  const last = Math.max(1, Math.round(timing.duration * fps));
  if (drag === "move") {
    const length = clamp(
      Math.round((item.t_end - item.t_start) * fps),
      1,
      last,
    );
    const start = clamp(Math.round(span.start * fps), 0, last - length);
    return { start: start / fps, end: (start + length) / fps };
  }
  let start = clamp(Math.round(span.start * fps), 0, last - 1);
  let end = clamp(Math.round(span.end * fps), 1, last);
  if (end <= start) {
    if (drag === "start") start = end - 1;
    else end = start + 1;
  }
  return { start: start / fps, end: end / fps };
}

/** Whether span differs from item's (by more than a microsecond). */
export function spanChanged(item: EdlItem, span: Span): boolean {
  return (
    Math.abs(item.t_start - span.start) > 1e-6 ||
    Math.abs(item.t_end - span.end) > 1e-6
  );
}

/** items with item id at span (its other fields kept). */
export function withSpan(items: EdlItem[], id: number, span: Span): EdlItem[] {
  return items.map((item) =>
    item.id === id ? { ...item, t_start: span.start, t_end: span.end } : item,
  );
}

/** What a guide says it snapped to, e.g. 'word "why"', "beat". */
export function guideLabel(guide: SnapTarget): string {
  if (guide.kind === "word") return `word “${guide.text ?? ""}”`;
  if (guide.kind === "item") return "item edge";
  return guide.kind;
}
