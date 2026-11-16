import { useState } from "react";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { useEditorShortcuts } from "@/hooks/useEditorShortcuts";
import type { PreviewPlayer } from "@/hooks/usePreviewPlayer";
import type { TimelineState } from "@/hooks/useTimelineState";
import type { Undo } from "@/hooks/useUndo";
import {
  findItem,
  pastedItem,
  removeItem,
  type LayerItem,
} from "@/lib/layerItems";
import { layerLength } from "@/lib/layers";
import { stepRate } from "@/lib/playbackRate";
import { sourceToPreview } from "@/lib/timeline";
import type { TimelineActions } from "@/lib/timelineActions";

export interface TimelineKeyInput {
  edits: ClipEdits;
  actions: TimelineActions;
  timeline: TimelineState;
  player: PreviewPlayer;
  undo: Undo;
  /** The source time the player is at. */
  playhead: number;
  /** Unselect the transcript's words. */
  clearWords: () => void;
}

export interface TimelineKeys {
  /** The selected layer item and its track, if any. */
  item: LayerItem | null;
  /** Select a layer item (the words and the segment are unselected). */
  selectItem: (id: string) => void;
  /** Something is selected that Delete removes. */
  canDelete: boolean;
  /** Remove the selected layer item, else cut the selected segment or
   * words (TimelineActions); false if nothing is selected. */
  deleteSelection: () => boolean;
}

/**
 * The editor's keyboard (useEditorShortcuts) over its timeline: play/pause,
 * frame and 1 s steps, split, zoom, undo/redo (useUndo), playback speed
 * (< / >), and a selected layer item's Delete, copy (cmd+C) and paste at
 * the playhead on the same track (cmd+V; the copy gets a new id and is
 * kept inside the clip). Escape unselects words and items.
 */
export function useTimelineKeys(input: TimelineKeyInput): TimelineKeys {
  const { edits, actions, timeline, player, undo, playhead } = input;
  const [clipboard, setClipboard] = useState<LayerItem | null>(null);
  const item = findItem(edits.layers, timeline.item);

  const deleteSelection = () => {
    if (!item) return actions.deleteSelection();
    const { name } = item;
    edits.setLayer(name, removeItem(edits.layers[name], item.item.id));
    timeline.selectItem(null);
    return true;
  };

  const copy = () => {
    if (item) setClipboard(item);
    return item !== null;
  };

  const paste = () => {
    if (!clipboard) return false;
    const { name } = clipboard;
    const { range, cuts, layers } = edits;
    const at = sourceToPreview(playhead, range, cuts);
    const pasted = pastedItem(
      layers,
      clipboard.item,
      at,
      layerLength(range, cuts),
    );
    edits.setLayer(name, [...layers[name], pasted]);
    timeline.selectItem(pasted.id);
    return true;
  };

  const selectItem = (id: string) => {
    timeline.selectItem(id);
    input.clearWords();
  };

  useEditorShortcuts({
    togglePlay: player.toggle,
    deleteSelection,
    clearSelection: () => {
      input.clearWords();
      timeline.selectItem(null);
    },
    undo: undo.undo,
    redo: undo.redo,
    split: actions.split,
    zoom: timeline.zoomSteps,
    step: actions.step,
    copy,
    paste,
    speed: (steps) => player.setRate(stepRate(player.rate, steps)),
  });

  return {
    item,
    selectItem,
    canDelete: item !== null || actions.canDelete,
    deleteSelection,
  };
}
