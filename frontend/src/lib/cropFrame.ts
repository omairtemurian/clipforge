/**
 * The crop tool's math, in source pixels: where a clip's fill window is at
 * a source time (the same rules as the backend's pipeline/framing), and
 * how dragging moves or resizes it inside the source frame.
 */
import type { CropPoint, CropTrack, Framing } from "@/api/types";

/** A window of the source frame: its top-left corner and size, in pixels. */
export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A corner of the crop window, by compass direction. */
export type Corner = "nw" | "ne" | "sw" | "se";

/** The smallest crop window, as a fraction of the planned window. */
export const MIN_SCALE = 0.25;

/** Points closer in time than this replace each other. */
export const POINT_GAP_S = 0.1;

/** A framing that keeps the crop plan as it is. */
export const DEFAULT_FRAMING: Framing = {
  aspect: null,
  background: "blur",
  scale: 1,
  points: [],
  tracker: true,
  facecam: null,
};

const clamp = (value: number, low: number, high: number) =>
  Math.min(Math.max(value, low), high);

/** value rounded down to an even number of pixels. */
export const even = (value: number) => Math.floor(value / 2) * 2;

/** The value at t of the line through (times[k], values[k]), held before
 * the first and after the last; 0 without values. */
export function interpolate(
  times: number[],
  values: number[],
  t: number,
): number {
  if (values.length === 0) return 0;
  const k = times.findIndex((time) => time > t);
  if (k === 0) return values[0];
  if (k === -1) return values[values.length - 1];
  const [t0, t1, v0, v1] = [times[k - 1], times[k], values[k - 1], values[k]];
  return t1 > t0 ? v0 + ((v1 - v0) * (t - t0)) / (t1 - t0) : v1;
}

/** Whether framing changes the fill window (points, size or tracker off). */
export function usesCropTool(framing: Framing): boolean {
  return framing.points.length > 0 || framing.scale < 1 || !framing.tracker;
}

/** The planned window's center at each of track's times, shifted by the
 * crop offset (a fraction of its width) and kept inside the frame. */
function trackedCenters(track: CropTrack, offset: number): number[] {
  const shift = Math.round((offset * track.width) / 2) * 2;
  const right = track.frame_width - track.width;
  return track.xs.map(
    (x) => clamp(Math.max(x + shift, 0), 0, right) + track.width / 2,
  );
}

/** The even start of a window of size centered at center, inside 0..limit. */
export function place(center: number, size: number, limit: number): number {
  return Math.max(
    0,
    Math.min(even(Math.round(center - size / 2)), even(limit - size)),
  );
}

/**
 * The clip's fill window at source time t: track (the planned window)
 * nudged by offset, then sized and placed by framing's crop tool. With the
 * tracker on it follows the plan, moved to be at each point at its time;
 * with it off it is at the points (or the plan's first window).
 */
export function cropWindowAt(
  track: CropTrack,
  framing: Framing,
  offset: number,
  t: number,
): Rect {
  const { frame_width: frameWidth, frame_height: frameHeight } = track;
  const width = Math.max(2, even(Math.round(track.width * framing.scale)));
  const height = Math.max(2, even(Math.round(track.height * framing.scale)));
  const times = track.times.length > 0 ? track.times : [t];
  const tracked =
    track.times.length > 0 ? trackedCenters(track, offset) : [frameWidth / 2];
  const points = [...framing.points].sort((a, b) => a.t - b.t);
  const pointTimes = points.map((point) => point.t);
  const pointXs = points.map((point) => point.x * frameWidth);
  let center: number;
  if (framing.tracker) {
    const shifts = points.map(
      (point, k) => pointXs[k] - interpolate(times, tracked, point.t),
    );
    center =
      interpolate(times, tracked, t) + interpolate(pointTimes, shifts, t);
  } else if (points.length > 0) {
    center = interpolate(pointTimes, pointXs, t);
  } else {
    center = tracked[0];
  }
  const middle =
    points.length > 0
      ? interpolate(
          pointTimes,
          points.map((point) => point.y * frameHeight),
          t,
        )
      : track.y + track.height / 2;
  return {
    x: place(center, width, frameWidth),
    y: place(middle, height, frameHeight),
    width,
    height,
  };
}

/** rect moved by (dx, dy) source pixels, kept inside the frame. */
export function moveRect(
  rect: Rect,
  dx: number,
  dy: number,
  frame: { width: number; height: number },
): Rect {
  return {
    ...rect,
    x: clamp(rect.x + dx, 0, frame.width - rect.width),
    y: clamp(rect.y + dy, 0, frame.height - rect.height),
  };
}

/**
 * rect resized by dragging corner by (dx, dy) source pixels: the opposite
 * corner stays, the shape stays, the width stays between minWidth and
 * maxWidth and the window inside the frame.
 */
export function resizeRect(
  rect: Rect,
  corner: Corner,
  dx: number,
  dy: number,
  frame: { width: number; height: number },
  limits: { minWidth: number; maxWidth: number },
): Rect {
  const ratio = rect.width / rect.height;
  const east = corner === "ne" || corner === "se";
  const south = corner === "sw" || corner === "se";
  const growX = east ? dx : -dx;
  const growY = (south ? dy : -dy) * ratio;
  const grow = Math.abs(growX) >= Math.abs(growY) ? growX : growY;
  const anchorX = east ? rect.x : rect.x + rect.width;
  const anchorY = south ? rect.y : rect.y + rect.height;
  const roomX = east ? frame.width - anchorX : anchorX;
  const roomY = (south ? frame.height - anchorY : anchorY) * ratio;
  const maxWidth = Math.min(limits.maxWidth, roomX, roomY);
  const width = clamp(
    rect.width + grow,
    Math.min(limits.minWidth, maxWidth),
    maxWidth,
  );
  const height = width / ratio;
  return {
    x: east ? anchorX : anchorX - width,
    y: south ? anchorY : anchorY - height,
    width,
    height,
  };
}

/**
 * rect resized by dragging corner by (dx, dy) source pixels, in any shape:
 * the opposite corner stays, each side is at least minSize and the box
 * stays inside the frame.
 */
export function resizeFree(
  rect: Rect,
  corner: Corner,
  dx: number,
  dy: number,
  frame: { width: number; height: number },
  minSize: number,
): Rect {
  const east = corner === "ne" || corner === "se";
  const south = corner === "sw" || corner === "se";
  const anchorX = east ? rect.x : rect.x + rect.width;
  const anchorY = south ? rect.y : rect.y + rect.height;
  const roomX = east ? frame.width - anchorX : anchorX;
  const roomY = south ? frame.height - anchorY : anchorY;
  const width = clamp(
    rect.width + (east ? dx : -dx),
    Math.min(minSize, roomX),
    roomX,
  );
  const height = clamp(
    rect.height + (south ? dy : -dy),
    Math.min(minSize, roomY),
    roomY,
  );
  return {
    x: east ? anchorX : anchorX - width,
    y: south ? anchorY : anchorY - height,
    width,
    height,
  };
}

/** points with point added, replacing any within POINT_GAP_S of it. */
export function setPoint(points: CropPoint[], point: CropPoint): CropPoint[] {
  return [
    ...points.filter((other) => Math.abs(other.t - point.t) >= POINT_GAP_S),
    point,
  ].sort((a, b) => a.t - b.t);
}

/** The point of framing at source time t, if there is one. */
export function pointAt(framing: Framing, t: number): CropPoint | undefined {
  return framing.points.find((point) => Math.abs(point.t - t) < POINT_GAP_S);
}

const round = (value: number, digits: number) =>
  Math.round(value * 10 ** digits) / 10 ** digits;

/** framing with the crop window set to rect at source time t: its size
 * for the whole clip, and a point (keyframe) at t. */
export function framingWithRect(
  framing: Framing,
  rect: Rect,
  t: number,
  track: CropTrack,
): Framing {
  const point = {
    t: round(t, 3),
    x: clamp(round((rect.x + rect.width / 2) / track.frame_width, 4), 0, 1),
    y: clamp(round((rect.y + rect.height / 2) / track.frame_height, 4), 0, 1),
  };
  return {
    ...framing,
    scale: clamp(round(rect.width / track.width, 3), MIN_SCALE, 1),
    points: setPoint(framing.points, point),
  };
}
