import { describe, expect, it } from "vitest";
import type { CropTrack } from "@/api/types";
import { DEFAULT_FRAMING } from "@/lib/cropFrame";
import {
  boxToRect,
  facecamRect,
  isFacecamLayout,
  middleRect,
  rectToBox,
} from "@/lib/facecam";

const FRAME = { width: 1280, height: 720 };
const TRACK: CropTrack = {
  aspect: "9:16",
  frame_width: 1280,
  frame_height: 720,
  width: 404,
  height: 720,
  y: 0,
  times: [10],
  xs: [100],
  facecam: { x: 0.5, y: 0.1, width: 0.25, height: 0.4 },
};

describe("facecam box", () => {
  it("tells the facecam layouts", () => {
    expect(isFacecamLayout("screenshare")).toBe(true);
    expect(isFacecamLayout("gameplay")).toBe(true);
    expect(isFacecamLayout("fill")).toBe(false);
    expect(isFacecamLayout("pip")).toBe(false);
  });

  it("turns boxes into pixels and back, inside the frame", () => {
    const box = { x: 0.5, y: 0.1, width: 0.25, height: 0.4 };
    expect(boxToRect(box, FRAME)).toEqual({
      x: 640,
      y: 72,
      width: 320,
      height: 288,
    });
    expect(rectToBox(boxToRect(box, FRAME), FRAME)).toEqual(box);
    // Rounded to 4 digits; a box past the edge is cut at it.
    expect(
      rectToBox({ x: 1000, y: 500, width: 400, height: 300 }, FRAME),
    ).toEqual({ x: 0.7813, y: 0.6944, width: 0.2187, height: 0.3056 });
  });

  it("shows the drawn box, else the found one, else the middle", () => {
    const drawn = { x: 0, y: 0, width: 0.5, height: 0.5 };
    expect(facecamRect({ ...DEFAULT_FRAMING, facecam: drawn }, TRACK)).toEqual({
      rect: { x: 0, y: 0, width: 640, height: 360 },
      source: "drawn",
    });
    expect(facecamRect(DEFAULT_FRAMING, TRACK).source).toBe("found");
    const none = facecamRect(DEFAULT_FRAMING, { ...TRACK, facecam: null });
    expect(none).toEqual({ rect: middleRect(FRAME), source: "none" });
    expect(middleRect(FRAME)).toEqual({
      x: 520,
      y: 240,
      width: 240,
      height: 240,
    });
  });
});
