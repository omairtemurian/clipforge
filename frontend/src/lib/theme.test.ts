import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  applyTheme,
  readTheme,
  resolveTheme,
  saveTheme,
  THEME_COLORS,
  THEME_KEY,
} from "./theme";

// Vitest runs from frontend/.
const HTML = readFileSync("index.html", "utf8");
const INIT_SCRIPT = /<script id="theme-init">([\s\S]*?)<\/script>/.exec(
  HTML,
)![1];

/** Stub matchMedia so the OS asks for dark (or not). */
function osPrefersDark(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: dark && query === "(prefers-color-scheme: dark)",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

/** Run index.html's inline script on a fresh document. */
function runInitScript() {
  document.documentElement.className = "";
  document.head.innerHTML = '<meta name="theme-color" content="" />';
  new Function(INIT_SCRIPT)();
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
  document.documentElement.className = "";
});

describe("theme choice", () => {
  it("is Light on a fresh profile and for junk in storage", () => {
    expect(readTheme()).toBe("light");
    localStorage.setItem(THEME_KEY, "sepia");
    expect(readTheme()).toBe("light");
  });

  it("resolves System from the OS and keeps explicit choices", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
  });

  it("saves the choice and applies it to the document", () => {
    osPrefersDark(false);
    document.head.innerHTML = '<meta name="theme-color" content="" />';
    expect(saveTheme("dark")).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
    expect(
      document
        .querySelector('meta[name="theme-color"]')!
        .getAttribute("content"),
    ).toBe(THEME_COLORS.dark);

    applyTheme("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });
});

describe("index.html first-paint script", () => {
  it.each([
    [null, false, "light"],
    ["light", true, "light"],
    ["dark", false, "dark"],
    ["system", true, "dark"],
    ["system", false, "light"],
    ["sepia", true, "light"],
  ] as const)(
    "saved %s with an OS dark=%s paints %s, like lib/theme",
    (saved, dark, expected) => {
      if (saved !== null) localStorage.setItem(THEME_KEY, saved);
      osPrefersDark(dark);
      runInitScript();
      const painted = document.documentElement.classList.contains("dark")
        ? "dark"
        : "light";
      expect(painted).toBe(expected);
      expect(painted).toBe(resolveTheme(readTheme(), dark));
      expect(
        document
          .querySelector('meta[name="theme-color"]')!
          .getAttribute("content"),
      ).toBe(THEME_COLORS[expected]);
    },
  );

  it("runs before the app module", () => {
    expect(HTML.indexOf('id="theme-init"')).toBeLessThan(
      HTML.indexOf('src="/src/main.tsx"'),
    );
  });
});
