import { describe, expect, it } from "vitest";
import type { CropTrack, Framing } from "@/api/types";
import {
  cropWindowAt,
  DEFAULT_FRAMING,
  framingWithRect,
  interpolate,
  moveRect,
  pointAt,
  resizeFree,
  resizeRect,
  setPoint,
  usesCropTool,
  type Rect,
} from "./cropFrame";

const FRAME = { width: 1280, height: 720 };
const LIMITS = { minWidth: 101, maxWidth: 404 };

/** The 404x720 window of 9:16 in 1280x720, left edge xs[k] at 10 + k s. */
function track(...xs: number[]): CropTrack {
  return {
    aspect: "9:16",
    frame_width: 1280,
    frame_height: 720,
    width: 404,
    height: 720,
    y: 0,
    times: xs.map((_, k) => 10 + k),
    xs,
    facecam: null,
  };
}

function framing(changes: Partial<Framing>): Framing {
  return { ...DEFAULT_FRAMING, ...changes };
}

const point = (t: number, x: number, y = 0.5) => ({ t, x, y });

describe("interpolate", () => {
  it("is linear between values and holds outside", () => {
    expect(interpolate([10, 12], [100, 200], 9)).toBe(100);
    expect(interpolate([10, 12], [100, 200], 11)).toBe(150);
    expect(interpolate([10, 12], [100, 200], 13)).toBe(200);
    expect(interpolate([], [], 11)).toBe(0);
  });
});

describe("cropWindowAt", () => {
  it("is the planned window, nudged and kept inside, by default", () => {
    expect(usesCropTool(DEFAULT_FRAMING)).toBe(false);
    expect(cropWindowAt(track(300, 500), DEFAULT_FRAMING, 0, 10.5)).toEqual({
      x: 400,
      y: 0,
      width: 404,
      height: 720,
    });
    expect(cropWindowAt(track(400, 400), DEFAULT_FRAMING, 0.5, 10).x).toBe(602);
    expect(cropWindowAt(track(800, 800), DEFAULT_FRAMING, 1, 10).x).toBe(876);
  });

  it("with the tracker on, is at each point and follows the plan between", () => {
    const at = (t: number) =>
      cropWindowAt(
        track(300, 400, 500),
        framing({ points: [point(11, 0.5)] }),
        0,
        t,
      ).x;
    expect([at(10), at(11), at(12)]).toEqual([338, 438, 538]);
  });

  it("with the tracker off, stays where the points put it", () => {
    const off = framing({
      tracker: false,
      points: [point(10, 0.25), point(12, 0.75)],
    });
    const at = (t: number) => cropWindowAt(track(300, 400, 500), off, 0, t).x;
    expect([at(10), at(11), at(12)]).toEqual([118, 438, 758]);
    expect(
      cropWindowAt(track(300, 400), framing({ tracker: false }), 0, 11).x,
    ).toBe(300);
  });

  it("sizes the window by scale and keeps it inside the frame", () => {
    const small = framing({ scale: 0.5, points: [point(10, 0.25, 0.25)] });
    expect(cropWindowAt(track(400, 400), small, 0, 10)).toEqual({
      x: 218,
      y: 0,
      width: 202,
      height: 360,
    });
    const corner = framing({ scale: 0.5, points: [point(10, 1, 1)] });
    expect(cropWindowAt(track(400), corner, 0, 10)).toMatchObject({
      x: 1078,
      y: 360,
    });
  });
});

describe("moveRect", () => {
  const rect: Rect = { x: 400, y: 100, width: 202, height: 360 };

  it("moves the window by the drag", () => {
    expect(moveRect(rect, 50, -20, FRAME)).toEqual({ ...rect, x: 450, y: 80 });
  });

  it("clamps the window inside the frame", () => {
    expect(moveRect(rect, -1000, -1000, FRAME)).toMatchObject({ x: 0, y: 0 });
    expect(moveRect(rect, 5000, 5000, FRAME)).toMatchObject({
      x: 1078,
      y: 360,
    });
  });
});

describe("resizeRect", () => {
  const rect: Rect = { x: 400, y: 100, width: 202, height: 360 };
  const ratio = rect.width / rect.height;

  it("keeps the opposite corner and the shape", () => {
    const grown = resizeRect(rect, "se", 40, 0, FRAME, LIMITS);
    expect(grown).toMatchObject({ x: 400, y: 100, width: 242 });
    expect(grown.width / grown.height).toBeCloseTo(ratio);

    const fromTopLeft = resizeRect(rect, "nw", 20, 0, FRAME, LIMITS);
    expect(fromTopLeft.width).toBe(182);
    expect(fromTopLeft.x + fromTopLeft.width).toBe(602);
    expect(fromTopLeft.y + fromTopLeft.height).toBeCloseTo(460);
    expect(fromTopLeft.width / fromTopLeft.height).toBeCloseTo(ratio);
  });

  it("follows the larger of the two moves", () => {
    const tall = resizeRect(rect, "se", 0, 90, FRAME, LIMITS);
    expect(tall.height).toBeCloseTo(450);
    expect(tall.width / tall.height).toBeCloseTo(ratio);
  });

  it("clamps the size between the limits and inside the frame", () => {
    expect(resizeRect(rect, "se", -500, 0, FRAME, LIMITS).width).toBe(101);
    const top = { ...rect, y: 0 };
    expect(resizeRect(top, "se", 900, 0, FRAME, LIMITS).width).toBeCloseTo(404);
    // From y 300 the frame leaves 420 px of height below the window.
    const low = { ...rect, y: 300 };
    const bottom = resizeRect(low, "se", 900, 0, FRAME, LIMITS);
    expect(bottom.y + bottom.height).toBeCloseTo(720);
    expect(bottom.width / bottom.height).toBeCloseTo(ratio);
    const left = resizeRect({ ...rect, x: 50 }, "sw", -900, 0, FRAME, LIMITS);
    expect(left.x).toBeCloseTo(0);
    expect(left.width).toBeCloseTo(252);
  });
});

describe("resizeFree", () => {
  const rect = { x: 400, y: 200, width: 200, height: 100 };

  it("resizes each side on its own from the opposite corner", () => {
    expect(resizeFree(rect, "se", 40, 60, FRAME, 20)).toEqual({
      x: 400,
      y: 200,
      width: 240,
      height: 160,
    });
    expect(resizeFree(rect, "nw", 50, -30, FRAME, 20)).toEqual({
      x: 450,
      y: 170,
      width: 150,
      height: 130,
    });
  });

  it("keeps each side at least minSize and the box inside the frame", () => {
    expect(resizeFree(rect, "se", -900, -900, FRAME, 20)).toEqual({
      x: 400,
      y: 200,
      width: 20,
      height: 20,
    });
    expect(resizeFree(rect, "ne", 900, -900, FRAME, 20)).toEqual({
      x: 400,
      y: 0,
      width: 880,
      height: 300,
    });
  });
});

describe("points", () => {
  it("replace each other when close in time and stay sorted", () => {
    const points = setPoint(
      [point(12, 0.1), point(10, 0.2)],
      point(12.05, 0.9),
    );
    expect(points).toEqual([point(10, 0.2), point(12.05, 0.9)]);
    expect(pointAt(framing({ points }), 12)).toEqual(point(12.05, 0.9));
    expect(pointAt(framing({ points }), 11)).toBeUndefined();
  });

  it("are made from a dragged window with its scale", () => {
    const rect: Rect = { x: 219, y: 0, width: 202, height: 360 };
    const next = framingWithRect(DEFAULT_FRAMING, rect, 10.25, track(400));
    expect(next.scale).toBe(0.5);
    expect(next.points).toEqual([{ t: 10.25, x: 0.25, y: 0.25 }]);
    expect(cropWindowAt(track(400), next, 0, 10.25)).toMatchObject({
      x: 218,
      y: 0,
    });
  });
});
