/**
 * What the editor's timeline buttons and keys do with the clip's edits:
 * split at the playhead, delete the selected segment or words, skip
 * between segment edges and step the playhead.
 */
import type { Word } from "@/api/types";
import type { ClipEdits } from "@/hooks/useClipEdits";
import type { TimelineState } from "@/hooks/useTimelineState";
import { selectionSpan, type WordSelection } from "@/lib/cuts";
import {
  adjacentPoint,
  canCutSegment,
  segments,
  snapToWords,
  SNAP_SPLIT_S,
} from "@/lib/segments";
import { sourceToPreview, type CutRange } from "@/lib/timeline";

export interface TimelineActionInput {
  edits: ClipEdits;
  /** The edges between the clip's scenes, which split segments too. */
  sceneBounds?: number[];
  timeline: TimelineState;
  words: Word[] | undefined;
  selection: WordSelection | null;
  clearSelection: () => void;
  /** The source time the player is at, and seeking to a source time. */
  playhead: number;
  seek: (t: number) => void;
  /** The preview's time, and seeking to a preview time. */
  previewTime: number;
  seekPreview: (t: number) => void;
}

export interface TimelineActions {
  /** The kept parts of the edited clip. */
  parts: CutRange[];
  /** The selected segment, if it is still a part of the clip. */
  selected: CutRange | null;
  canDelete: boolean;
  /** Cut the selected segment, else the selected words; false if neither. */
  deleteSelection: () => boolean;
  split: () => void;
  skip: (direction: -1 | 1) => void;
  step: (seconds: number) => void;
}

/** The timeline actions of the editor's current state (input). */
export function timelineActions(input: TimelineActionInput): TimelineActions {
  const { edits, timeline, words, selection, playhead } = input;
  const edges = [...edits.splits, ...(input.sceneBounds ?? [])];
  const parts = segments(
    edits.range,
    [...new Set(edges)].sort((a, b) => a - b),
    edits.cuts,
  );
  const chosen = timeline.selected;
  const selected =
    (chosen && parts.find(([a, b]) => a === chosen[0] && b === chosen[1])) ??
    null;
  const wordSpan = selection && words ? selectionSpan(words, selection) : null;
  const canDelete = selected ? canCutSegment(parts, selected) : !!wordSpan;

  return {
    parts,
    selected,
    canDelete,
    deleteSelection: () => {
      if (!canDelete) return false;
      edits.cut(selected ?? (wordSpan as CutRange));
      timeline.select(null);
      input.clearSelection();
      return true;
    },
    split: () => {
      const snapped =
        timeline.snap && words
          ? snapToWords(playhead, words, SNAP_SPLIT_S)
          : playhead;
      edits.split(snapped);
    },
    skip: (direction) => {
      // In preview time, so both edges of a cut are one point.
      const edges = [...parts.flat(), ...edits.splits];
      const points = edges.map((t) =>
        sourceToPreview(t, edits.range, edits.cuts),
      );
      const fallback = direction < 0 ? 0 : Math.max(0, ...points);
      input.seekPreview(
        adjacentPoint(points, input.previewTime, direction) ?? fallback,
      );
    },
    step: (seconds) =>
      input.seekPreview(Math.max(0, input.previewTime + seconds)),
  };
}
