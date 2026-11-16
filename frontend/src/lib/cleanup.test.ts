import { describe, expect, it } from "vitest";
import type { CleanupSuggestion } from "@/api/types";
import {
  cleanupCuts,
  isApplied,
  strengthLabel,
  suggestionLabel,
} from "./cleanup";

const UM: CleanupSuggestion = {
  start: 6.2,
  end: 7.55,
  kind: "filler",
  text: "um",
};
const PAUSE: CleanupSuggestion = {
  start: 13.65,
  end: 16.75,
  kind: "pause",
  text: "",
};
const LIKE: CleanupSuggestion = {
  start: 22.6,
  end: 24.15,
  kind: "filler",
  text: "like",
};
const ALL = [UM, PAUSE, LIKE];

describe("cleanupCuts", () => {
  it("cuts every checked suggestion", () => {
    expect(cleanupCuts(ALL, new Set(), [])).toEqual([
      [6.2, 7.55],
      [13.65, 16.75],
      [22.6, 24.15],
    ]);
  });

  it("leaves out an unchecked suggestion's cut range", () => {
    expect(cleanupCuts(ALL, new Set([1]), [])).toEqual([
      [6.2, 7.55],
      [22.6, 24.15],
    ]);
    expect(cleanupCuts(ALL, new Set([0, 1, 2]), [])).toEqual([]);
  });

  it("leaves out suggestions the clip's cuts already remove", () => {
    const cuts: [number, number][] = [[6, 8]];
    expect(isApplied(UM, cuts)).toBe(true);
    expect(isApplied(PAUSE, [[14, 20]])).toBe(false);
    expect(cleanupCuts(ALL, new Set(), cuts)).toEqual([
      [13.65, 16.75],
      [22.6, 24.15],
    ]);
  });

  it("labels fillers by their words, bad takes by theirs and pauses as Pause", () => {
    expect(suggestionLabel(UM)).toBe("“um”");
    expect(suggestionLabel(PAUSE)).toBe("Pause");
    expect(
      suggestionLabel({
        start: 1,
        end: 3,
        kind: "bad_take",
        text: "Then I bought",
      }),
    ).toBe("Then I bought");
  });

  it("shows the enhancement strength as a percentage", () => {
    expect(strengthLabel(0)).toBe("Off");
    expect(strengthLabel(0.65)).toBe("65%");
  });
});
