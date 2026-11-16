import { describe, expect, it } from "vitest";
import { punchCount } from "@/lib/zoom";

describe("punchCount", () => {
  it("counts the rises from scale 1", () => {
    const keys = [
      { t: 12, scale: 1 },
      { t: 12.2, scale: 1.15 },
      { t: 14.2, scale: 1.15 },
      { t: 14.7, scale: 1 },
      { t: 20, scale: 1 },
      { t: 20.2, scale: 1.12 },
      { t: 22.7, scale: 1 },
    ];
    expect(punchCount(keys)).toBe(2);
    expect(punchCount([])).toBe(0);
    expect(
      punchCount([
        { t: 1, scale: 1.1 },
        { t: 2, scale: 1 },
      ]),
    ).toBe(1);
  });
});
