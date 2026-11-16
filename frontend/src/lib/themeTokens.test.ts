import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { contrast, over, parseColor, type Rgba } from "@/testing/contrast";

// Vitest runs from frontend/.
const CSS = readFileSync("src/index.css", "utf8");

/** The custom properties of one `selector { ... }` block of index.css. */
function block(selector: string): Record<string, string> {
  const start = CSS.indexOf(`\n${selector} {`);
  const body = CSS.slice(start, CSS.indexOf("\n}", start));
  const tokens: Record<string, string> = {};
  for (const match of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    tokens[match[1]] = match[2].trim();
  }
  return tokens;
}

const LIGHT = block(":root");
const THEMES = { light: LIGHT, dark: { ...LIGHT, ...block(".dark") } };

function color(tokens: Record<string, string>, name: string): Rgba {
  let value = tokens[name];
  for (let ref = /^var\(--([\w-]+)\)$/.exec(value); ref;) {
    value = tokens[ref[1]];
    ref = /^var\(--([\w-]+)\)$/.exec(value);
  }
  return parseColor(value);
}

const WHITE = parseColor("#ffffff");
const BLACK = parseColor("#000000");

/** Text token over surface token; `tint` lays the surface (at that alpha)
 * over the card first, like `bg-primary/15` pills. */
const PAIRS: [text: string, surface: string, tint?: number][] = [
  ["foreground", "background"],
  ["foreground", "muted"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["secondary-foreground", "secondary"],
  ["muted-foreground", "background"],
  ["muted-foreground", "card"],
  ["muted-foreground", "muted"],
  ["primary-foreground", "primary"],
  ["primary-ink", "background"],
  ["primary-ink", "card"],
  ["primary-ink", "primary", 0.15],
  ["accent-foreground", "accent"],
  ["destructive", "card"],
  ["destructive", "background"],
  ["destructive", "destructive", 0.15],
  ["success", "card"],
  ["success", "background"],
  ["success", "success", 0.15],
  ["warning", "card"],
  ["warning", "background"],
  ["warning", "warning", 0.15],
  ["sidebar-foreground", "sidebar"],
  ["sidebar-accent-foreground", "sidebar-accent"],
];

describe("theme tokens", () => {
  it.each(Object.entries(THEMES))(
    "%s: every text token keeps WCAG AA (4.5:1) on its surfaces",
    (_, tokens) => {
      const failures: string[] = [];
      const card = color(tokens, "card");
      for (const [text, surface, tint] of PAIRS) {
        const base = color(tokens, surface);
        const behind =
          tint === undefined
            ? over(base, card)
            : over({ ...base, a: tint }, card);
        const ratio = contrast(over(color(tokens, text), behind), behind);
        if (ratio < 4.5)
          failures.push(`${text} on ${surface}: ${ratio.toFixed(2)}`);
      }
      expect(failures).toEqual([]);
    },
  );

  it.each(Object.entries(THEMES))(
    "%s: pills on the overlay stay readable over any thumbnail",
    (_, tokens) => {
      for (const image of [WHITE, BLACK]) {
        const behind = over(color(tokens, "overlay"), image);
        expect(
          contrast(color(tokens, "foreground"), behind),
        ).toBeGreaterThanOrEqual(4.5);
      }
    },
  );

  it("keeps ClipForge ember as the accent fill of both themes", () => {
    expect(LIGHT.ember).toBe("#ff6b35");
    expect(color(THEMES.light, "primary")).toEqual(
      color(THEMES.dark, "primary"),
    );
  });

  it("matches the reference style in Light: light grey page, white cards, hairline borders", () => {
    expect(LIGHT.background).toBe("#f5f5f7");
    expect(LIGHT.card).toBe("#ffffff");
    expect(LIGHT.border).toBe("#ececee");
    expect(LIGHT.secondary).toBe("#f1f1f3");
    expect(LIGHT["elevation-card"]).toBe(
      "0 1px 2px rgb(0 0 0 / 4%), 0 8px 24px rgb(0 0 0 / 6%)",
    );
  });

  it("uses Poppins in four bundled weights", () => {
    expect(CSS).toMatch(/--font-sans:\s*"Poppins"/);
    for (const weight of ["Regular", "Medium", "SemiBold", "Bold"]) {
      expect(CSS).toContain(`url("/fonts/Poppins-${weight}.ttf")`);
    }
  });
});
