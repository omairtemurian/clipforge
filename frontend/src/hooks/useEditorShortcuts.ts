import { useEffect, useRef } from "react";
import { FRAME_S } from "@/lib/timeline";

/** What the editor's keyboard shortcuts do. */
export interface EditorShortcutHandlers {
  togglePlay: () => void;
  /** Cut the selected words; false if no words are selected. */
  deleteSelection: () => boolean;
  clearSelection: () => void;
  undo: () => void;
  redo: () => void;
  /** Split the clip at the playhead. */
  split: () => void;
  /** Zoom the timeline steps steps in (positive) or out. */
  zoom: (steps: number) => void;
  /** Move the playhead by seconds (negative: back). */
  step: (seconds: number) => void;
  /** Copy the selected timeline item; false if none is selected. */
  copy: () => boolean;
  /** Paste the copied item at the playhead; false if none is copied. */
  paste: () => boolean;
  /** Play steps speeds faster (positive) or slower. */
  speed: (steps: number) => void;
}

const TEXT_INPUTS = "input, textarea, select, [contenteditable='true']";
const OWN_SPACE = "button, a[href], [role='slider'], [role='button']";
const OWN_ARROWS = "[role='slider']";
const ZOOM_KEYS: Record<string, number> = { "+": 1, "=": 1, "-": -1, _: -1 };
const SPEED_KEYS: Record<string, number> = { ">": 1, "<": -1 };

function targetElement(event: KeyboardEvent): Element | null {
  return event.target instanceof Element ? event.target : null;
}

/**
 * Handle a keydown of the editor: cmd/ctrl+Z undoes, shift+cmd/ctrl+Z and
 * ctrl+Y redo, Delete/Backspace cut the selected words, Escape clears the
 * selection and Space plays or pauses (unless a button or slider has the
 * focus, where Space is its own). S splits at the playhead, +/- zoom the
 * timeline, left/right step the playhead a frame (shift: 1 s) unless a
 * slider has the focus, < and > slow down or speed up playback, and
 * cmd/ctrl+C / cmd/ctrl+V copy the selected timeline item and paste it at
 * the playhead (with no item selected or copied they are the browser's).
 * Keys typed into a text field are its own.
 */
export function handleEditorKey(
  event: KeyboardEvent,
  handlers: EditorShortcutHandlers,
): void {
  const target = targetElement(event);
  if (event.defaultPrevented || target?.closest(TEXT_INPUTS)) return;
  const key = event.key.toLowerCase();
  const command = event.metaKey || event.ctrlKey;

  if (command && key === "z") {
    event.preventDefault();
    if (event.shiftKey) handlers.redo();
    else handlers.undo();
  } else if (event.ctrlKey && key === "y") {
    event.preventDefault();
    handlers.redo();
  } else if (command && !event.shiftKey && (key === "c" || key === "v")) {
    if (key === "c" ? handlers.copy() : handlers.paste()) {
      event.preventDefault();
    }
  } else if (command || event.altKey) {
    return;
  } else if (key === "delete" || key === "backspace") {
    if (handlers.deleteSelection()) event.preventDefault();
  } else if (key === "escape") {
    handlers.clearSelection();
  } else if (key === " " && !target?.closest(OWN_SPACE)) {
    event.preventDefault();
    handlers.togglePlay();
  } else if (key === "s" && !event.shiftKey) {
    event.preventDefault();
    handlers.split();
  } else if (key in ZOOM_KEYS) {
    event.preventDefault();
    handlers.zoom(ZOOM_KEYS[key]);
  } else if (key in SPEED_KEYS) {
    event.preventDefault();
    handlers.speed(SPEED_KEYS[key]);
  } else if (
    (key === "arrowleft" || key === "arrowright") &&
    !target?.closest(OWN_ARROWS)
  ) {
    event.preventDefault();
    const seconds = event.shiftKey ? 1 : FRAME_S;
    handlers.step(key === "arrowleft" ? -seconds : seconds);
  }
}

/** Listen for the editor's keyboard shortcuts (handleEditorKey) on the
 * window while mounted, with the latest handlers. */
export function useEditorShortcuts(handlers: EditorShortcutHandlers): void {
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) =>
      handleEditorKey(event, latest.current);
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
