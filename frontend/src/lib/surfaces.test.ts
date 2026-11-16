import { describe, expect, it } from "vitest";
import { cardClass, choiceClass, pageColumn } from "./surfaces";

describe("surfaces", () => {
  it("lays out a page column", () => {
    expect(pageColumn("wide")).toContain("max-w-wide");
    expect(pageColumn()).toContain("max-w-form");
  });

  it("adds the hover lift to an interactive card", () => {
    expect(cardClass()).not.toContain("hover:shadow-card-hover");
    expect(cardClass(true)).toContain("hover:shadow-card-hover");
  });

  it("tints a chosen row and lifts the others", () => {
    const chosen = choiceClass(true).split(" ");
    expect(chosen).toEqual(
      expect.arrayContaining(["border-primary", "bg-primary/10"]),
    );
    expect(chosen).not.toContain("border-border");
    expect(chosen).not.toContain("bg-card");
    const other = choiceClass(false).split(" ");
    expect(other).toEqual(
      expect.arrayContaining(["border-border", "bg-card", "rounded-xl"]),
    );
    expect(other).toContain("focus-visible:ring-3");
  });
});
