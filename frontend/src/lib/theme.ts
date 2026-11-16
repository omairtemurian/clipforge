/**
 * The color theme: Light (the default), Dark or System (follows the OS).
 * The choice lives in localStorage; the inline script in index.html applies
 * it before first paint with the same rules as `resolveTheme`, so a reload
 * never flashes the wrong theme.
 */

export type ThemeChoice = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_KEY = "clipforge.theme";
export const THEME_CHOICES: ThemeChoice[] = ["light", "dark", "system"];

/** The browser bar color per theme (the page background). */
export const THEME_COLORS: Record<ResolvedTheme, string> = {
  light: "#f5f5f7",
  dark: "#1e1e20",
};

const DARK_QUERY = "(prefers-color-scheme: dark)";

/** The saved choice; Light when nothing (or junk) is saved. */
export function readTheme(): ThemeChoice {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    return THEME_CHOICES.includes(saved as ThemeChoice)
      ? (saved as ThemeChoice)
      : "light";
  } catch {
    return "light";
  }
}

/** Whether the OS asks for dark (false where matchMedia is missing). */
export function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function"
    ? window.matchMedia(DARK_QUERY).matches
    : false;
}

/** Light or dark for a choice; System follows the OS. */
export function resolveTheme(
  choice: ThemeChoice,
  prefersDark: boolean,
): ResolvedTheme {
  if (choice === "system") return prefersDark ? "dark" : "light";
  return choice;
}

/** Set the `dark` class, color-scheme and theme-color of the document. */
export function applyTheme(theme: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", THEME_COLORS[theme]);
}

/** Save a choice and apply it now. */
export function saveTheme(choice: ThemeChoice): ResolvedTheme {
  try {
    localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Private mode: the theme still applies for this page.
  }
  const theme = resolveTheme(choice, systemPrefersDark());
  applyTheme(theme);
  return theme;
}

/**
 * Call `onChange` when the OS switches between light and dark; returns the
 * unsubscribe function.
 */
export function watchSystemTheme(onChange: () => void): () => void {
  if (typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
