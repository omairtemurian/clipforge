import { describe, expect, it } from "vitest";
import { rateLabel, stepRate } from "./playbackRate";

describe("playback rate", () => {
  it("steps through the speeds and stops at the ends", () => {
    expect(stepRate(1, 1)).toBe(1.25);
    expect(stepRate(1, -1)).toBe(0.75);
    expect(stepRate(2, 1)).toBe(2);
    expect(stepRate(0.25, -1)).toBe(0.25);
    expect(stepRate(1.1, 1)).toBe(1.25);
  });

  it("labels a speed", () => {
    expect(rateLabel(0.5)).toBe("0.5×");
    expect(rateLabel(1)).toBe("1×");
  });
});
