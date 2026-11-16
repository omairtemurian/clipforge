/**
 * The layer tracks of a clip's timeline (every track but video): their
 * names and labels, what an item shows, and moving or trimming an item by
 * dragging (snapped, kept inside the rendered clip). Layer items are timed
 * in seconds of the rendered clip (its cuts left out).
 */
import type { Timeline, TrackItem } from "@/api/types";
import { snapSpan, snapTargets, snapTime, type Span } from "@/lib/snap";
import {
  clamp,
  FRAME_S,
  sourceToPreview,
  type ClipRange,
  type CutRange,
} from "@/lib/timeline";

/** The tracks of a clip other than video, which the editor moves. */
export type LayerTracks = Omit<Timeline, "video">;
export type LayerName = keyof LayerTracks;

/** The layer tracks in the order of SPEC-v2 3.5. */
export const LAYER_NAMES: LayerName[] = [
  "broll",
  "overlays",
  "text",
  "music",
  "sfx",
  "voiceover",
];

export const LAYER_LABELS: Record<LayerName, string> = {
  broll: "B-roll",
  overlays: "Overlays",
  text: "Text",
  music: "Music",
  sfx: "SFX",
  voiceover: "Voiceover",
};

const KIND_LABELS: Record<TrackItem["kind"], string> = {
  source: "Source",
  video: "Video",
  image: "Image",
  text: "Text",
  audio: "Audio",
};

/** The shortest an item can be trimmed to, in seconds. */
export const MIN_ITEM_S = 0.1;

/** What a drag does to an item: move it whole or move one of its edges. */
export type ItemDrag = "move" | "start" | "end";

/** The layer tracks of a timeline (its video track left out). */
export function layerTracks(timeline: Timeline): LayerTracks {
  const { broll, overlays, text, music, sfx, voiceover } = timeline;
  return { broll, overlays, text, music, sfx, voiceover };
}

/** What an item shows on its track: a text item's text, else its kind
 * and asset. */
export function itemLabel(item: TrackItem): string {
  if (item.kind === "text") {
    const text = item.props.text;
    return typeof text === "string" && text ? text : "Text";
  }
  const name = KIND_LABELS[item.kind];
  return item.asset_id == null ? name : `${name} #${item.asset_id}`;
}

/** The start and end of every layer item but the one with id except. */
export function layerEdges(layers: LayerTracks, except?: string): number[] {
  return LAYER_NAMES.flatMap((name) =>
    layers[name]
      .filter((item) => item.id !== except)
      .flatMap((item) => [item.start, item.end]),
  );
}

/**
 * How long a rendered clip of length seconds (its span less its cuts) is at
 * least: the render cuts on whole frames, which can shorten each cut part
 * by up to a frame.
 */
export function safeLength(length: number, cutCount: number): number {
  return Math.max(0, length - FRAME_S * cutCount);
}

/** The clip time layer items of clip (with cuts) must end by: its
 * rendered length less a frame per cut (safeLength). */
export function layerLength(clip: ClipRange, cuts: CutRange[]): number {
  return safeLength(sourceToPreview(clip.end, clip, cuts), cuts.length);
}

const ms = (t: number) => Math.round(t * 1000) / 1000;

/** span moved to start at start (its length kept), inside [0, length]. */
export function moveSpan(span: Span, start: number, length: number): Span {
  const size = Math.min(span.end - span.start, length);
  const from = clamp(start, 0, Math.max(0, length - size));
  return { start: ms(from), end: ms(from + size) };
}

/** span with its edge moved to t, inside [0, length] and at least
 * MIN_ITEM_S long (the other edge stays). */
export function trimSpan(
  span: Span,
  edge: "start" | "end",
  t: number,
  length: number,
): Span {
  if (edge === "start") {
    const latest = Math.max(0, span.end - MIN_ITEM_S);
    return { start: ms(clamp(t, 0, latest)), end: span.end };
  }
  const earliest = Math.min(length, span.start + MIN_ITEM_S);
  return { start: span.start, end: ms(clamp(t, earliest, length)) };
}

/** A drag of an item: what it does, the time under the pointer, how far
 * after the item's start it was grabbed, and what it snaps to. */
export interface DragInput {
  drag: ItemDrag;
  pointer: number;
  grab: number;
  targets: number[];
  tolerance: number;
  length: number;
}

/**
 * The span of an item after a drag: moved so its start is grab before the
 * pointer, its nearer edge snapped to a target, or the dragged edge moved
 * to the pointer (snapped); always inside [0, length].
 */
export function dragSpan(span: Span, input: DragInput): Span {
  const { drag, pointer, grab, targets, tolerance, length } = input;
  if (drag === "move") {
    const moved = moveSpan(span, pointer - grab, length);
    const snapped = snapSpan(moved, targets, tolerance);
    return moveSpan(span, snapped.start, length);
  }
  return trimSpan(span, drag, snapTime(pointer, targets, tolerance), length);
}

/** items with the item whose id is id at span instead. */
export function placeItem(
  items: TrackItem[],
  id: string,
  span: Span,
): TrackItem[] {
  return items.map((item) => (item.id === id ? { ...item, ...span } : item));
}

/** What a layer item snaps to, in source seconds (words and segments) or
 * clip seconds (layers). */
export interface LayerSnap {
  clip: ClipRange;
  cuts: CutRange[];
  /** Starts and ends of the transcript's words (source seconds). */
  words: number[];
  /** The kept parts of the clip (source seconds). */
  parts: CutRange[];
  /** The playhead (source seconds). */
  playhead: number;
  layers: LayerTracks;
  /** The id of the dragged item, which does not snap to itself. */
  except: string;
}

/**
 * The clip times (seconds after the cuts) a dragged layer item snaps to:
 * the word edges inside the clip, the edges of its segments, the playhead
 * and the edges of the other layer items.
 */
export function layerSnapTargets(snap: LayerSnap): number[] {
  const { clip, cuts } = snap;
  const toClip = (t: number) => sourceToPreview(t, clip, cuts);
  const inside = (t: number) => t >= clip.start && t <= clip.end;
  return snapTargets({
    words: snap.words.filter(inside).map(toClip),
    segments: snap.parts.flat().map(toClip),
    playhead: inside(snap.playhead) ? toClip(snap.playhead) : undefined,
    layers: layerEdges(snap.layers, snap.except),
  });
}
