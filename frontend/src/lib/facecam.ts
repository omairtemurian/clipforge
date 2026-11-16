/**
 * The facecam box of the screenshare and gameplay layouts (the backend's
 * pipeline/facecam): the part of the source frame that the facecam cell
 * shows. It is the box the user drew (Framing.facecam), else the one
 * reframe found around the subject's face (CropTrack.facecam); without
 * either the video takes the whole output.
 */
import type { Clip, CropTrack, FrameBox, Framing } from "@/api/types";
import type { Rect } from "@/lib/cropFrame";

type Layout = Clip["layout"];

/** The layouts that show a facecam box. */
export const FACECAM_LAYOUTS: readonly Layout[] = ["screenshare", "gameplay"];

/** The smallest side of a facecam box, as a fraction of the frame height. */
export const MIN_FACECAM = 0.05;

/** Where the facecam box being shown comes from. */
export type FacecamSource = "drawn" | "found" | "none";

type Frame = { width: number; height: number };

export const isFacecamLayout = (layout: Layout) =>
  FACECAM_LAYOUTS.includes(layout);

const round4 = (value: number) => Math.round(value * 10000) / 10000;

/** box (fractions of the frame) in source pixels of frame. */
export function boxToRect(box: FrameBox, frame: Frame): Rect {
  return {
    x: box.x * frame.width,
    y: box.y * frame.height,
    width: box.width * frame.width,
    height: box.height * frame.height,
  };
}

/** rect (source pixels of frame) as a box of fractions of the frame,
 * rounded to 4 digits and kept inside it. */
export function rectToBox(rect: Rect, frame: Frame): FrameBox {
  const x = Math.min(Math.max(round4(rect.x / frame.width), 0), 1);
  const y = Math.min(Math.max(round4(rect.y / frame.height), 0), 1);
  return {
    x,
    y,
    width: Math.max(Math.min(round4(rect.width / frame.width), 1 - x), 1e-4),
    height: Math.max(Math.min(round4(rect.height / frame.height), 1 - y), 1e-4),
  };
}

/** A square a third of the frame's height in its middle: where a new box
 * starts when reframe found no face. */
export function middleRect(frame: Frame): Rect {
  const side = Math.round(frame.height / 3);
  return {
    x: Math.round((frame.width - side) / 2),
    y: Math.round((frame.height - side) / 2),
    width: side,
    height: side,
  };
}

/** The facecam box to show for framing over track, in source pixels, and
 * where it comes from. */
export function facecamRect(
  framing: Framing,
  track: CropTrack,
): { rect: Rect; source: FacecamSource } {
  const frame = { width: track.frame_width, height: track.frame_height };
  if (framing.facecam) {
    return { rect: boxToRect(framing.facecam, frame), source: "drawn" };
  }
  if (track.facecam) {
    return { rect: boxToRect(track.facecam, frame), source: "found" };
  }
  return { rect: middleRect(frame), source: "none" };
}
