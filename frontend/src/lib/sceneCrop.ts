/**
 * The fill window of a fixed or tracked scene (the backend's
 * pipeline/scene_framing), in source pixels, and the crop tool's
 * keyframes on it: the window's center is at the scene's keyframes,
 * linear between them and held before the first and after the last; a
 * scene without keyframes holds the clip's window of its start.
 */
import type { CropPoint, CropTrack, Framing, SceneReframe } from "@/api/types";
import {
  cropWindowAt,
  DEFAULT_FRAMING,
  even,
  framingWithRect,
  place,
  POINT_GAP_S,
  setPoint,
  type Rect,
} from "@/lib/cropFrame";

/** The crop tool framing that puts a window where scene's keyframes do. */
function keyedFraming(scene: SceneReframe): Framing {
  return {
    ...DEFAULT_FRAMING,
    tracker: false,
    scale: scene.scale,
    points: scene.crop_keyframes,
  };
}

/**
 * The fill window of scene at source time t: at its keyframes, else the
 * clip's window (track nudged by offset and framed by framing) at the
 * scene's start, resized to the scene's scale about its center.
 */
export function sceneWindowAt(
  scene: SceneReframe,
  track: CropTrack,
  framing: Framing,
  offset: number,
  t: number,
): Rect {
  if (scene.crop_keyframes.length > 0) {
    return cropWindowAt(track, keyedFraming(scene), 0, t);
  }
  const auto = cropWindowAt(track, framing, offset, scene.start);
  const width = Math.max(2, even(Math.round(track.width * scene.scale)));
  const height = Math.max(2, even(Math.round(track.height * scene.scale)));
  return {
    x: place(auto.x + auto.width / 2, width, track.frame_width),
    y: place(auto.y + auto.height / 2, height, track.frame_height),
    width,
    height,
  };
}

/** scene with its window set to rect at source time t: its scale, and a
 * keyframe at t (replacing any within POINT_GAP_S). */
export function sceneWithRect(
  scene: SceneReframe,
  rect: Rect,
  t: number,
  track: CropTrack,
): SceneReframe {
  const framing = framingWithRect(keyedFraming(scene), rect, t, track);
  return { ...scene, scale: framing.scale, crop_keyframes: framing.points };
}

/** The keyframe of scene at source time t, if there is one. */
export function keyframeAt(
  scene: SceneReframe,
  t: number,
): CropPoint | undefined {
  return scene.crop_keyframes.find((key) => Math.abs(key.t - t) < POINT_GAP_S);
}

/** scene without its keyframe at time t (exactly). */
export function withoutKeyframe(scene: SceneReframe, t: number): SceneReframe {
  return {
    ...scene,
    crop_keyframes: scene.crop_keyframes.filter((key) => key.t !== t),
  };
}

/** scene with its keyframe at time from moved to time to, kept inside
 * the scene; it replaces keyframes within POINT_GAP_S of where it lands. */
export function movedKeyframe(
  scene: SceneReframe,
  from: number,
  to: number,
): SceneReframe {
  const key = scene.crop_keyframes.find((other) => other.t === from);
  if (!key) return scene;
  const t = Math.round(Math.min(Math.max(to, scene.start), scene.end) * 1000);
  const rest = scene.crop_keyframes.filter((other) => other !== key);
  return { ...scene, crop_keyframes: setPoint(rest, { ...key, t: t / 1000 }) };
}
