import { useReducer } from "react";
import type {
  Clip,
  ClipPatch,
  ClipTransitions,
  SceneReframe,
  TrackItem,
} from "@/api/types";
import { clipLook, type ClipLook } from "@/lib/clipLook";
import { addCut, mergeCuts, restoreCut, subtractCuts } from "@/lib/cuts";
import { historyReducer, initHistory, type History } from "@/lib/history";
import { layerTracks, type LayerName, type LayerTracks } from "@/lib/layers";
import { fitScenes } from "@/lib/scenes";
import { addSplit } from "@/lib/segments";
import { sameLayers } from "@/lib/tidyLayers";
import {
  fitCuts,
  moveHandle,
  type ClipRange,
  type CutRange,
  type Handle,
} from "@/lib/timeline";

/** The texts of a clip that the editor changes. */
export interface ClipTexts {
  title: string;
  hook_text: string;
  description: string;
  hashtags: string[];
}

/** The parts of a clip the editor changes: its span, its cut ranges
 * (kept as cut, also where the span no longer reaches), the timeline's
 * split points (editor only, not saved), its texts, its look
 * (layout, captions, crop), its scenes (none: framed as its layout), the
 * transitions at its cuts and the items of its layer tracks (saved with
 * PATCH /clips/{id}/tracks). */
export interface ClipEdit {
  range: ClipRange;
  cuts: CutRange[];
  splits: number[];
  texts: ClipTexts;
  look: ClipLook;
  scenes: SceneReframe[];
  transitions: ClipTransitions;
  layers: LayerTracks;
}

/** The PATCH /clips/{id} body that saves edit: span, cut ranges inside it,
 * title, hook, description and hashtags, layout, caption template, style and
 * word texts, the crop offset, the scenes (fitted to the span) and the
 * transitions. */
export function clipPatch(edit: ClipEdit): ClipPatch {
  return {
    start: edit.range.start,
    end: edit.range.end,
    cut_ranges: fitCuts(edit.cuts, edit.range),
    ...edit.texts,
    ...edit.look,
    scene_reframes: fitScenes(edit.scenes, edit.range),
    transitions: edit.transitions,
  };
}

export interface ClipEdits {
  range: ClipRange;
  /** The cut ranges inside the clip's span, merged and sorted. */
  cuts: CutRange[];
  /** The split points inside the clip's span, sorted. */
  splits: number[];
  texts: ClipTexts;
  /** The clip's layout, caption template, style and word texts, and crop
   * offset as edited now. */
  look: ClipLook;
  /** The clip's stored scenes, fitted to its span (none: framed as its
   * layout says throughout). */
  scenes: SceneReframe[];
  /** The transitions at the clip's jump cuts and between its sections. */
  transitions: ClipTransitions;
  /** The PATCH body that saves the edits (clipPatch). */
  patch: ClipPatch;
  /** The clip's layer tracks (all but video) as edited now. */
  layers: LayerTracks;
  /** Whether the layer tracks differ from the clip's saved ones. */
  layersDirty: boolean;
  /** Whether the edits differ from the clip as saved (splits are not saved). */
  dirty: boolean;
  /** Move the clip's span; moves of one gesture (a drag) undo at once. */
  setRange: (range: ClipRange, gesture?: number) => void;
  /** Cut span (trimmed to the clip) from the clip. */
  cut: (span: CutRange) => void;
  /** Cut all spans from the clip in one undoable step. */
  cutAll: (spans: CutRange[]) => void;
  /** Turn auto cut on (cut the silences autoCuts) or off (bring back what
   * they cut), in one undoable step. */
  setAutoCut: (on: boolean, autoCuts: CutRange[]) => void;
  /** Change the clip's title, hook, description and/or hashtags. */
  setTexts: (texts: Partial<ClipTexts>) => void;
  /** Change the clip's look; changes of one gesture (a slider drag) undo
   * at once. A new layout is also every stored scene's. */
  setLook: (look: Partial<ClipLook>, gesture?: number) => void;
  /** Store the clip's scenes and set its layout, in one undoable step
   * (with the other changes of gesture). */
  setScenes: (
    scenes: SceneReframe[],
    layout: Clip["layout"],
    gesture?: number,
  ) => void;
  /** Change the clip's transitions; changes of one gesture (a slider
   * drag) undo at once. */
  setTransitions: (transitions: ClipTransitions, gesture?: number) => void;
  /** Replace the items of a layer track; changes of one gesture (a drag)
   * undo at once. */
  setLayer: (name: LayerName, items: TrackItem[], gesture?: number) => void;
  /** Split the clip at source time t (addSplit). */
  split: (t: number) => void;
  /** Bring back the cut that removes source time t. */
  restore: (t: number) => void;
  /** Move the clip's start or end to source time t, inside bounds. */
  extend: (handle: Handle, t: number, bounds: ClipRange) => void;
  /** Start over from clip as saved, forgetting the edits and their history. */
  reset: (clip: Clip) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

function savedEdit(clip: Clip): ClipEdit {
  return {
    range: { start: clip.start, end: clip.end },
    cuts: mergeCuts(clip.cut_ranges),
    splits: [],
    texts: {
      title: clip.title,
      hook_text: clip.hook_text,
      description: clip.description,
      hashtags: clip.hashtags,
    },
    look: clipLook(clip),
    scenes: clip.scene_reframes,
    transitions: clip.transitions,
    layers: layerTracks(clip.tracks),
  };
}

function initEdit(clip: Clip): History<ClipEdit> {
  return initHistory(savedEdit(clip));
}

/**
 * The editor's unsaved changes of clip with their undo/redo history: its
 * span (timeline handles, "extend to here"), its cut ranges (deleted
 * words or segments), the timeline's split points, its texts, its look,
 * its transitions and its layer tracks.
 * `clip` follows the saved clip: after a save the edits are no longer dirty.
 */
export function useClipEdits(clip: Clip): ClipEdits {
  const [history, dispatch] = useReducer(
    historyReducer<ClipEdit>,
    clip,
    initEdit,
  );
  const { range, cuts, splits, texts, look, scenes, transitions, layers } =
    history.present;

  const saved = savedEdit(clip);
  const patch = clipPatch(history.present);
  const layersDirty = !sameLayers(layers, saved.layers);

  const change = (next: Partial<ClipEdit>, gesture?: number) =>
    dispatch({
      type: "set",
      value: { ...history.present, ...next },
      gesture,
    });

  return {
    range,
    cuts: fitCuts(cuts, range),
    splits: splits.filter((t) => t > range.start && t < range.end),
    texts,
    look,
    scenes: fitScenes(scenes, range),
    transitions,
    patch,
    layers,
    layersDirty,
    dirty:
      layersDirty || JSON.stringify(patch) !== JSON.stringify(clipPatch(saved)),
    setRange: (next, gesture) => change({ range: next }, gesture),
    cut: (span) => change({ cuts: addCut(cuts, span, range) }),
    cutAll: (spans) =>
      change({
        cuts: spans.reduce((all, span) => addCut(all, span, range), cuts),
      }),
    setAutoCut: (on, autoCuts) =>
      change({
        cuts: on
          ? autoCuts.reduce((all, span) => addCut(all, span, range), cuts)
          : subtractCuts(cuts, autoCuts),
        look: { ...look, auto_cut: on },
      }),
    setTexts: (next) => change({ texts: { ...texts, ...next } }),
    setLook: (next, gesture) => {
      const layout = next.layout;
      change(
        {
          look: { ...look, ...next },
          scenes: layout
            ? scenes.map((scene) => ({ ...scene, layout }))
            : scenes,
        },
        gesture,
      );
    },
    setScenes: (next, layout, gesture) =>
      change({ scenes: next, look: { ...look, layout } }, gesture),
    setTransitions: (next, gesture) => change({ transitions: next }, gesture),
    setLayer: (name, items, gesture) =>
      change({ layers: { ...layers, [name]: items } }, gesture),
    split: (t) => change({ splits: addSplit(splits, t, range) }),
    restore: (t) => change({ cuts: restoreCut(cuts, t) }),
    extend: (handle, t, bounds) =>
      change({ range: moveHandle(range, handle, t, bounds) }),
    reset: (saved) => dispatch({ type: "reset", value: savedEdit(saved) }),
    undo: () => dispatch({ type: "undo" }),
    redo: () => dispatch({ type: "redo" }),
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
  };
}
