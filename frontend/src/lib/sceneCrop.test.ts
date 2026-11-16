import { describe, expect, it } from "vitest";
import type { CropTrack, SceneReframe } from "@/api/types";
import { DEFAULT_FRAMING } from "@/lib/cropFrame";
import {
  keyframeAt,
  movedKeyframe,
  sceneWindowAt,
  sceneWithRect,
  withoutKeyframe,
} from "./sceneCrop";
import { autoScene } from "./scenes";

// The 404x720 window of 9:16 in 1280x720, left edge 100 at 10 s, 300 at 11 s.
const TRACK: CropTrack = {
  aspect: "9:16",
  frame_width: 1280,
  frame_height: 720,
  width: 404,
  height: 720,
  y: 0,
  times: [10, 11],
  xs: [100, 300],
  facecam: null,
};

const key = (t: number, x: number, y = 0.5) => ({ t, x, y });

function fixed(keys = [key(10, 0.25), key(12, 0.75)], scale = 1) {
  return {
    ...autoScene(10, 14, "fill"),
    mode: "fixed",
    crop_keyframes: keys,
    scale,
  } as SceneReframe;
}

describe("sceneWindowAt", () => {
  it("puts the window's center at the keyframes, linear between them", () => {
    const at = (t: number) =>
      sceneWindowAt(fixed(), TRACK, DEFAULT_FRAMING, 0, t);
    // Centers 320, 640 and 960 less half the 404 px width.
    expect(at(10)).toEqual({ x: 118, y: 0, width: 404, height: 720 });
    expect(at(11).x).toBe(438);
    expect(at(13).x).toBe(758);
  });

  it("holds the clip's window of the scene's start without keyframes", () => {
    const scene = { ...fixed([], 0.5), start: 11 };
    // The plan's window at 11 s is centered at 502; half size is 202x360.
    expect(sceneWindowAt(scene, TRACK, DEFAULT_FRAMING, 0, 10)).toEqual({
      x: 400,
      y: 180,
      width: 202,
      height: 360,
    });
  });
});

describe("keyframe editing", () => {
  it("sets a keyframe and the scale from a window", () => {
    const rect = { x: 438, y: 180, width: 202, height: 360 };
    const scene = sceneWithRect(fixed([]), rect, 11, TRACK);
    expect(scene.scale).toBe(0.5);
    expect(scene.crop_keyframes).toEqual([key(11, 0.4211)]);
    expect(keyframeAt(scene, 11.05)).toEqual(key(11, 0.4211));
    expect(keyframeAt(scene, 11.2)).toBeUndefined();
  });

  it("deletes and moves keyframes inside the scene", () => {
    expect(withoutKeyframe(fixed(), 10).crop_keyframes).toEqual([
      key(12, 0.75),
    ]);
    expect(movedKeyframe(fixed(), 10, 11.5).crop_keyframes).toEqual([
      key(11.5, 0.25),
      key(12, 0.75),
    ]);
    // Past the scene's end it stops there; landing on a keyframe replaces it.
    expect(movedKeyframe(fixed(), 10, 20).crop_keyframes).toEqual([
      key(12, 0.75),
      key(14, 0.25),
    ]);
    expect(movedKeyframe(fixed(), 10, 12.05).crop_keyframes).toEqual([
      key(12.05, 0.25),
    ]);
    expect(movedKeyframe(fixed(), 9, 11)).toEqual(fixed());
  });
});
