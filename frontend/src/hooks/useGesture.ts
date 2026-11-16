import { useRef } from "react";

let lastGesture = 0;

/** A new gesture id, unique among all the editor's gestures (drags). */
export function nextGesture(): number {
  lastGesture += 1;
  return lastGesture;
}

/**
 * The id of the gesture a control is in, for edits that undo at once: a new
 * one starts when `begin` is called (pointer down or focus on the control).
 */
export function useGesture() {
  const id = useRef(0);
  return {
    current: () => id.current || (id.current = nextGesture()),
    begin: () => {
      id.current = nextGesture();
    },
  };
}
