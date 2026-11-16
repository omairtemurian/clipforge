import { useSyncExternalStore } from "react";
import {
  applyTheme,
  readTheme,
  resolveTheme,
  saveTheme,
  systemPrefersDark,
  THEME_KEY,
  watchSystemTheme,
  type ResolvedTheme,
  type ThemeChoice,
} from "@/lib/theme";

const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

/** Re-apply the saved choice (OS switched, or another tab saved one). */
function refresh() {
  applyTheme(resolveTheme(readTheme(), systemPrefersDark()));
  notify();
}

function onStorage(event: StorageEvent) {
  if (event.key === THEME_KEY) refresh();
}

let stopWatching: (() => void) | null = null;

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    stopWatching = watchSystemTheme(refresh);
    window.addEventListener("storage", onStorage);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      stopWatching?.();
      window.removeEventListener("storage", onStorage);
    }
  };
}

function snapshot(): string {
  const choice = readTheme();
  return `${choice}:${resolveTheme(choice, systemPrefersDark())}`;
}

/**
 * The theme choice (Light, Dark, System), the theme it resolves to, and a
 * setter that saves and applies it; every user of the hook updates together.
 */
export function useTheme(): {
  choice: ThemeChoice;
  theme: ResolvedTheme;
  setChoice: (choice: ThemeChoice) => void;
} {
  const [choice, theme] = useSyncExternalStore(subscribe, snapshot).split(
    ":",
  ) as [ThemeChoice, ResolvedTheme];
  return {
    choice,
    theme,
    setChoice: (next) => {
      saveTheme(next);
      notify();
    },
  };
}
