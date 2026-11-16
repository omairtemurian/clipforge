import type { TrackSeed } from "@/api/types";

/** A drag shorter than this (pixels on screen) is a click. */
const CLICK_PX = 4;

/** A point in fractions of the frame's width (x) and height (y). */
export interface FramePoint {
  x: number;
  y: number;
}

const round4 = (value: number) => Math.round(value * 10000) / 10000;

/**
 * The seed of a pick from a to b (frame fractions) at source time t: a
 * click (no size) if they are less than CLICK_PX apart on a frame of
 * width x height screen pixels, else the box they span.
 */
export function pickSeed(
  a: FramePoint,
  b: FramePoint,
  t: number,
  screen: { width: number; height: number },
): TrackSeed {
  const dx = (b.x - a.x) * screen.width;
  const dy = (b.y - a.y) * screen.height;
  if (Math.hypot(dx, dy) < CLICK_PX) {
    return { t, x: round4(a.x), y: round4(a.y), width: 0, height: 0 };
  }
  return {
    t,
    x: round4(Math.min(a.x, b.x)),
    y: round4(Math.min(a.y, b.y)),
    width: round4(Math.abs(b.x - a.x)),
    height: round4(Math.abs(b.y - a.y)),
  };
}
