import { useRef, type PointerEvent as ReactPointerEvent } from "react";
import { nextGesture } from "./useGesture";

/**
 * Pointer handlers that call onMove with the pointer's x while it is held
 * down (from the press on), and the id of this press (gesture); the element
 * captures the pointer meanwhile.
 */
export function useDrag(onMove: (clientX: number, gesture: number) => void) {
  const active = useRef(false);
  const gesture = useRef(0);
  return {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => {
      if (event.button !== 0) return;
      event.stopPropagation();
      active.current = true;
      gesture.current = nextGesture();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      onMove(event.clientX, gesture.current);
    },
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => {
      if (active.current) onMove(event.clientX, gesture.current);
    },
    onPointerUp: () => {
      active.current = false;
    },
    onPointerCancel: () => {
      active.current = false;
    },
  };
}

/**
 * Pointer handlers for a drag that starts from a press: onStart runs on the
 * press and returns what the drag needs to remember (e.g. where the pointer
 * grabbed); onMove then gets the pointer's x with it and the id of the press
 * (gesture), once the pointer has moved threshold px (a click moves
 * nothing). The element captures the pointer meanwhile. onEnd, if given,
 * runs when the press ends (released or cancelled) with whether it moved.
 */
export function useDragFrom<T>(
  onStart: (clientX: number) => T,
  onMove: (clientX: number, start: T, gesture: number) => void,
  threshold = 3,
  onEnd?: (moved: boolean, cancelled: boolean) => void,
) {
  const press = useRef<{ x: number; start: T; moved: boolean } | null>(null);
  const gesture = useRef(0);
  const finish = (cancelled: boolean) => {
    const current = press.current;
    press.current = null;
    if (current) onEnd?.(current.moved, cancelled);
  };
  return {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => {
      if (event.button !== 0) return;
      event.stopPropagation();
      gesture.current = nextGesture();
      press.current = {
        x: event.clientX,
        start: onStart(event.clientX),
        moved: false,
      };
      event.currentTarget.setPointerCapture?.(event.pointerId);
    },
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => {
      const current = press.current;
      if (!current) return;
      if (!current.moved && Math.abs(event.clientX - current.x) < threshold) {
        return;
      }
      current.moved = true;
      onMove(event.clientX, current.start, gesture.current);
    },
    onPointerUp: () => finish(false),
    onPointerCancel: () => finish(true),
  };
}
