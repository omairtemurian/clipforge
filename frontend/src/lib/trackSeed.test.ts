import { describe, expect, it } from "vitest";
import { pickSeed } from "@/lib/trackSeed";

const SCREEN = { width: 640, height: 360 };

describe("pickSeed", () => {
  it("is a click without a size when the pointer moved under 4 px", () => {
    expect(
      pickSeed({ x: 0.5, y: 0.25 }, { x: 0.504, y: 0.255 }, 12.3, SCREEN),
    ).toEqual({ t: 12.3, x: 0.5, y: 0.25, width: 0, height: 0 });
  });

  it("is the box spanned by a drag, in any direction, to 4 digits", () => {
    expect(
      pickSeed({ x: 0.6, y: 0.7 }, { x: 0.123456, y: 0.2 }, 3, SCREEN),
    ).toEqual({ t: 3, x: 0.1235, y: 0.2, width: 0.4765, height: 0.5 });
  });
});
