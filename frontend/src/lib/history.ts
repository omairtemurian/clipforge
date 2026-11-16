/**
 * An undo/redo history of a value: the values before the present one
 * (past, oldest first), the present one, and the undone ones (future,
 * next first).
 */
export interface History<T> {
  past: T[];
  present: T;
  future: T[];
  /** The gesture (a drag) of the last change, so its moves undo at once. */
  gesture: number | null;
}

export type HistoryAction<T> =
  /** Change the present value; changes of one gesture are one step. */
  | { type: "set"; value: T; gesture?: number }
  | { type: "undo" }
  | { type: "redo" }
  /** Start over from value, with nothing to undo or redo. */
  | { type: "reset"; value: T };

/** The most steps the history keeps to undo. */
export const HISTORY_LIMIT = 100;

/** A history whose present value is value, with nothing to undo or redo. */
export function initHistory<T>(value: T): History<T> {
  return { past: [], present: value, future: [], gesture: null };
}

/** Whether two values are the same data (plain JSON-like values). */
function same<T>(a: T, b: T): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

/**
 * The history after action. "set" with the present value changes nothing;
 * "set" with the gesture of the change before it replaces that change's
 * value (one step for a whole drag); any other "set" makes the present value
 * a step to undo (at most HISTORY_LIMIT are kept) and forgets the undone
 * ones. "undo" and "redo" with nothing to undo or redo change nothing.
 */
export function historyReducer<T>(
  state: History<T>,
  action: HistoryAction<T>,
): History<T> {
  switch (action.type) {
    case "set": {
      if (same(action.value, state.present)) return state;
      const gesture = action.gesture ?? null;
      if (gesture !== null && gesture === state.gesture) {
        return { ...state, present: action.value, future: [] };
      }
      return {
        past: [...state.past, state.present].slice(-HISTORY_LIMIT),
        present: action.value,
        future: [],
        gesture,
      };
    }
    case "undo": {
      if (state.past.length === 0) return state;
      return {
        past: state.past.slice(0, -1),
        present: state.past[state.past.length - 1],
        future: [state.present, ...state.future],
        gesture: null,
      };
    }
    case "redo": {
      if (state.future.length === 0) return state;
      return {
        past: [...state.past, state.present],
        present: state.future[0],
        future: state.future.slice(1),
        gesture: null,
      };
    }
    case "reset":
      return initHistory(action.value);
  }
}
