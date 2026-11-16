import { describe, expect, it } from "vitest";
import {
  MIN_CLIP_S,
  contextWindow,
  fitCuts,
  moveHandle,
  previewToSource,
  pxToTime,
  sourceToPreview,
  spanPercent,
  tickStep,
  ticks,
  timeToPx,
  ZOOM_MAX,
  ZOOM_MIN,
  zoomBy,
  zoomScroll,
} from "./timeline";

const VIEW = { from: 10, to: 70, width: 600 };
const CLIP = { start: 40, end: 70 };
const BOUNDS = { start: 10, end: 100 };

describe("px <-> time", () => {
  it("maps source seconds to pixels and back", () => {
    expect(timeToPx(10, VIEW)).toBe(0);
    expect(timeToPx(40, VIEW)).toBe(300);
    expect(timeToPx(70, VIEW)).toBe(600);
    expect(pxToTime(300, VIEW)).toBe(40);
    expect(pxToTime(150, VIEW)).toBe(25);
  });

  it("clamps pixels outside the track to the view", () => {
    expect(pxToTime(-50, VIEW)).toBe(10);
    expect(pxToTime(900, VIEW)).toBe(70);
  });

  it("survives an empty view or a track without width", () => {
    expect(timeToPx(30, { from: 5, to: 5, width: 600 })).toBe(0);
    expect(pxToTime(30, { ...VIEW, width: 0 })).toBe(10);
  });

  it("gives a span as clamped percentages", () => {
    const window = { start: 10, end: 70 };
    expect(spanPercent(25, 40, window)).toEqual({ left: 25, width: 25 });
    const before = spanPercent(0, 20, window);
    expect(before.left).toBe(0);
    expect(before.width).toBeCloseTo(50 / 3, 9);
    expect(spanPercent(80, 90, window)).toEqual({ left: 100, width: 0 });
  });
});

describe("contextWindow", () => {
  it("adds 30 s around the clip inside the video", () => {
    expect(contextWindow({ start: 40, end: 70 }, 600)).toEqual({
      start: 10,
      end: 100,
    });
    expect(contextWindow({ start: 5, end: 50 }, 60)).toEqual({
      start: 0,
      end: 60,
    });
  });

  it("has no upper end while the duration is unknown", () => {
    expect(contextWindow({ start: 5, end: 50 }, 0)).toEqual({
      start: 0,
      end: 80,
    });
  });
});

describe("moveHandle", () => {
  it("moves only the dragged handle", () => {
    expect(moveHandle(CLIP, "start", 30, BOUNDS)).toEqual({
      start: 30,
      end: 70,
    });
    expect(moveHandle(CLIP, "end", 85.5, BOUNDS)).toEqual({
      start: 40,
      end: 85.5,
    });
  });

  it("clamps a handle to the window", () => {
    expect(moveHandle(CLIP, "start", 2, BOUNDS).start).toBe(10);
    expect(moveHandle(CLIP, "end", 140, BOUNDS).end).toBe(100);
  });

  it("keeps the minimum length between the handles", () => {
    expect(moveHandle(CLIP, "start", 69.8, BOUNDS)).toEqual({
      start: 70 - MIN_CLIP_S,
      end: 70,
    });
    expect(moveHandle(CLIP, "end", 20, BOUNDS)).toEqual({
      start: 40,
      end: 40 + MIN_CLIP_S,
    });
    expect(moveHandle(CLIP, "end", 41, BOUNDS, 5).end).toBe(45);
  });
});

describe("fitCuts", () => {
  it("trims, drops, sorts and merges cut ranges to the clip", () => {
    const cuts: [number, number][] = [
      [60, 65],
      [35, 42],
      [72, 80],
      [50, 52],
      [51, 55],
    ];
    expect(fitCuts(cuts, CLIP)).toEqual([
      [40, 42],
      [50, 55],
      [60, 65],
    ]);
  });
});

describe("preview <-> source time", () => {
  const cuts: [number, number][] = [
    [45, 50],
    [60, 62],
  ];

  it("skips the cut ranges", () => {
    expect(previewToSource(0, CLIP, cuts)).toBe(40);
    expect(previewToSource(4, CLIP, cuts)).toBe(44);
    expect(previewToSource(5, CLIP, cuts)).toBe(50);
    expect(previewToSource(12, CLIP, cuts)).toBe(57);
    expect(previewToSource(15, CLIP, cuts)).toBe(62);
    expect(previewToSource(99, CLIP, cuts)).toBe(70);
  });

  it("maps a source time back, a cut one to the cut's end", () => {
    expect(sourceToPreview(44, CLIP, cuts)).toBe(4);
    expect(sourceToPreview(47, CLIP, cuts)).toBe(5);
    expect(sourceToPreview(57, CLIP, cuts)).toBe(12);
    expect(sourceToPreview(66, CLIP, cuts)).toBe(19);
    expect(sourceToPreview(20, CLIP, cuts)).toBe(0);
    expect(sourceToPreview(90, CLIP, cuts)).toBe(23);
  });
});

describe("ruler ticks", () => {
  it("picks the smallest round step that leaves room for labels", () => {
    expect(tickStep(90, 1200)).toBe(5);
    expect(tickStep(90, 300)).toBe(30);
    expect(tickStep(10, 1200)).toBe(1);
    expect(tickStep(0, 1200)).toBe(600);
  });

  it("lists the multiples of the step in the window", () => {
    expect(ticks(12, 41, 10)).toEqual([20, 30, 40]);
    expect(ticks(0, 2, 0.5)).toEqual([0, 0.5, 1, 1.5, 2]);
  });
});

describe("zoom", () => {
  it("steps by 1.5x inside its range", () => {
    expect(zoomBy(1, 1)).toBe(1.5);
    expect(zoomBy(1.5, 2)).toBe(3.375);
    expect(zoomBy(3, -1)).toBe(2);
    expect(zoomBy(ZOOM_MIN, -1)).toBe(ZOOM_MIN);
    expect(zoomBy(9, 1)).toBe(ZOOM_MAX);
  });

  it("keeps the playhead where it was on screen", () => {
    // Playhead at 25% of the view, 1000 px wide, unscrolled: x = 250.
    const scroll = zoomScroll({
      anchor: 0.25,
      viewport: 1000,
      scroll: 0,
      from: 1,
      to: 2,
    });
    expect(0.25 * 2000 - scroll).toBe(250);
  });

  it("centers a playhead that was out of sight", () => {
    const scroll = zoomScroll({
      anchor: 0.5,
      viewport: 1000,
      scroll: 0,
      from: 4,
      to: 4.5,
    });
    expect(0.5 * 4500 - scroll).toBe(500);
  });

  it("stays inside the content", () => {
    const zoomOut = { anchor: 0.5, viewport: 1000, scroll: 1500, from: 4 };
    expect(zoomScroll({ ...zoomOut, to: 1 })).toBe(0);
    const atEnd = { anchor: 1, viewport: 1000, scroll: 1000, from: 2 };
    expect(zoomScroll({ ...atEnd, to: 3 })).toBe(2000);
  });
});
