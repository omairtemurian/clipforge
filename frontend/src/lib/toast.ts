import { useSyncExternalStore } from "react";

export type ToastKind = "error" | "success" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const AUTO_DISMISS_MS = 6000;

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit(next: Toast[]) {
  toasts = next;
  listeners.forEach((listener) => listener());
}

/** Remove the toast with this id (no-op when it is already gone). */
export function dismissToast(id: number) {
  emit(toasts.filter((item) => item.id !== id));
}

/** Remove every toast. */
export function clearToasts() {
  emit([]);
}

/** Show a toast that disappears after a few seconds; returns its id. */
export function showToast(kind: ToastKind, message: string): number {
  const id = nextId++;
  emit([...toasts, { id, kind, message }]);
  setTimeout(() => dismissToast(id), AUTO_DISMISS_MS);
  return id;
}

export const toast = {
  error: (message: string) => showToast("error", message),
  success: (message: string) => showToast("success", message),
  info: (message: string) => showToast("info", message),
};

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The toasts on screen, re-rendering the component when they change. */
export function useToasts(): Toast[] {
  return useSyncExternalStore(
    subscribe,
    () => toasts,
    () => toasts,
  );
}
