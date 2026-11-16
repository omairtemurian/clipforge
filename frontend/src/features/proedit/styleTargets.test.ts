import { describe, expect, it } from "vitest";
import { DETAIL, METRICS } from "@/testing/styleRecipeFixtures";
import {
  addTarget,
  formatValue,
  groupMetrics,
  moveTarget,
  removeTarget,
  sliderBounds,
  snap,
} from "./styleTargets";

const [CUTS, LUMA, BPM] = METRICS;
const TARGETS = DETAIL.targets;

describe("style recipe targets", () => {
  it("groups the metrics in their order", () => {
    expect(groupMetrics(METRICS).map(([group]) => group)).toEqual([
      "rhythm",
      "look",
      "audio",
    ]);
  });

  it("formats values with their unit", () => {
    expect(formatValue(42, CUTS)).toBe("42/min");
    expect(formatValue(0.304, LUMA)).toBe("30%");
    expect(formatValue(140, BPM)).toBe("140 BPM");
    expect(snap(0.1 + 0.2, 0.01)).toBe(0.3);
  });

  it("widens a slider to hold the measured range", () => {
    expect(sliderBounds(CUTS, undefined)).toEqual({ min: 0, max: 120 });
    expect(
      sliderBounds(CUTS, { median: 130, low: 100, high: 150, count: 2 }),
    ).toEqual({ min: 0, max: 150 });
  });

  it("moves the range with the target, inside the slider", () => {
    expect(moveTarget(TARGETS, CUTS, 60).metrics.cuts_per_minute).toEqual({
      median: 60,
      low: 48,
      high: 72,
      count: 2,
    });
    expect(moveTarget(TARGETS, CUTS, 5).metrics.cuts_per_minute).toEqual({
      median: 5,
      low: 0,
      high: 17,
      count: 2,
    });
    expect(moveTarget(TARGETS, BPM, 100)).toBe(TARGETS);
  });

  it("sets and clears a target by hand", () => {
    const added = addTarget(TARGETS, BPM);
    expect(added.metrics.bpm).toEqual({
      median: 130,
      low: 122,
      high: 138,
      count: 0,
    });
    const cleared = removeTarget(added, CUTS);
    expect(Object.keys(cleared.metrics)).toEqual(["mean_luma", "bpm"]);
    expect(cleared.caption_color).toBe("#ffd000");
  });
});
