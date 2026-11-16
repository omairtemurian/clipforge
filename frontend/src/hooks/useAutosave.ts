import { useEffect, useRef, useState } from "react";

/** How long (ms) the edits rest before autosave saves them. */
export const AUTOSAVE_DELAY_MS = 2000;
const STORAGE_KEY = "clipforge.autosave";

/** What autosave is doing: off, nothing to save, waiting for the edits to
 * rest (or for a render or invalid texts to clear), saving, or its last
 * save of these edits failed. */
export type AutosaveStatus = "off" | "saved" | "pending" | "saving" | "failed";

export interface AutosaveInput {
  /** The edits differ from the saved clip. */
  dirty: boolean;
  /** The edits as data: a new value restarts the wait. */
  edits: string;
  /** Saving cannot happen now (invalid texts, a render, a save). */
  blocked: boolean;
  saving: boolean;
  /** Save the edits; true if saved. */
  save: () => Promise<boolean>;
  delay?: number;
}

export interface Autosave {
  on: boolean;
  toggle: () => void;
  status: AutosaveStatus;
}

function storedOn(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

/**
 * Autosave of the editor: once the edits have not changed for delay ms
 * (debounce) and can be saved, save them. A failed save is not retried
 * until the edits change (apiFetch has shown why). Autosave is on unless
 * the user turned it off (kept in localStorage).
 */
export function useAutosave({
  dirty,
  edits,
  blocked,
  saving,
  save,
  delay = AUTOSAVE_DELAY_MS,
}: AutosaveInput): Autosave {
  const [on, setOn] = useState(storedOn);
  const [failed, setFailed] = useState<string | null>(null);
  const latestSave = useRef(save);
  useEffect(() => {
    latestSave.current = save;
  });

  useEffect(() => {
    if (!on || !dirty || blocked || edits === failed) return;
    const timer = window.setTimeout(() => {
      void latestSave.current().then((saved) => {
        if (!saved) setFailed(edits);
      });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [on, dirty, blocked, edits, failed, delay]);

  const toggle = () => {
    const next = !on;
    setOn(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? "on" : "off");
    } catch {
      // Storage is unavailable (private mode): the choice lasts this page.
    }
  };

  let status: AutosaveStatus = "pending";
  if (!on) status = "off";
  else if (saving) status = "saving";
  else if (!dirty) status = "saved";
  else if (edits === failed) status = "failed";
  return { on, toggle, status };
}
