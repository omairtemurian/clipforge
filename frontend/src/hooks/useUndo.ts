import { useClipVersions, useMoveClipHistory } from "@/api/clipVersions";
import type { ClipHistory } from "@/api/types";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { toast } from "@/lib/toast";

/** Where an undo or redo goes: the editor's own edits ("local"), the
 * clip's saved versions ("server"), or nowhere (null). */
export type UndoTarget = "local" | "server" | null;

/** What decides where an undo or redo goes. */
export interface UndoState {
  /** The editor's edits differ from the saved clip. */
  dirty: boolean;
  canUndoLocal: boolean;
  canRedoLocal: boolean;
  /** The clip's saved history, if loaded. */
  history: ClipHistory | undefined;
  /** A save, render or history move is under way (no history moves). */
  busy: boolean;
}

/**
 * Where an undo goes: unsaved edits undo locally; once the edits are saved
 * (autosave does it), undo moves to the version before the saved one, so it
 * reaches past what was edited since the editor opened. Without a loaded
 * history it stays local.
 */
export function undoTarget(state: UndoState): UndoTarget {
  if (state.dirty) return state.canUndoLocal ? "local" : null;
  if (state.history?.can_undo && !state.busy) return "server";
  return state.canUndoLocal ? "local" : null;
}

/**
 * Where a redo goes: an edit undone locally comes back locally first; with
 * none, a saved clip redoes the version undone after it.
 */
export function redoTarget(state: UndoState): UndoTarget {
  if (state.canRedoLocal) return "local";
  if (!state.dirty && state.history?.can_redo && !state.busy) return "server";
  return null;
}

export interface Undo {
  canUndo: boolean;
  canRedo: boolean;
  undo: () => void;
  redo: () => void;
  /** The clip's saved versions and the current one, once loaded. */
  history: ClipHistory | undefined;
  /** Give the clip version number's state as a new version; true if done. */
  restore: (number: number) => Promise<boolean>;
  /** A history move (undo, redo, restore) is under way on the server. */
  moving: boolean;
}

/**
 * Undo/redo of the editor (top bar, cmd+Z / shift+cmd+Z) across the
 * editor's edits and the clip's saved versions (undoTarget, redoTarget),
 * and the version list with restore. A move on the server answers the
 * clip in that version; the editor's edits start over from it.
 * busy: a save or render is under way.
 */
export function useUndo(clipId: number, edits: ClipEdits, busy: boolean): Undo {
  const history = useClipVersions(clipId).data;
  const move = useMoveClipHistory(clipId);
  const state: UndoState = {
    dirty: edits.dirty,
    canUndoLocal: edits.canUndo,
    canRedoLocal: edits.canRedo,
    history,
    busy: busy || move.isPending,
  };
  const undoTo = undoTarget(state);
  const redoTo = redoTarget(state);

  const serverMove = async (
    request: Parameters<typeof move.mutateAsync>[0],
  ): Promise<boolean> => {
    try {
      edits.reset(await move.mutateAsync(request));
      return true;
    } catch {
      return false; // apiFetch has shown the error
    }
  };

  return {
    canUndo: undoTo !== null,
    canRedo: redoTo !== null,
    undo: () => {
      if (undoTo === "local") edits.undo();
      else if (undoTo === "server") void serverMove({ type: "undo" });
    },
    redo: () => {
      if (redoTo === "local") edits.redo();
      else if (redoTo === "server") void serverMove({ type: "redo" });
    },
    history,
    restore: async (number) => {
      const done = await serverMove({ type: "restore", number });
      if (done) toast.success(`Restored version ${number}.`);
      return done;
    },
    moving: move.isPending,
  };
}
