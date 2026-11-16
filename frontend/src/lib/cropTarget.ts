import type { CropPoint, CropTrack } from "@/api/types";
import type { ClipEdits } from "@/hooks/useClipEdits";
import type { SceneEdits } from "@/hooks/useSceneEdits";
import {
  cropWindowAt,
  framingWithRect,
  pointAt,
  type Rect,
} from "@/lib/cropFrame";
import {
  keyframeAt,
  sceneWindowAt,
  sceneWithRect,
  withoutKeyframe,
} from "@/lib/sceneCrop";

/** What the crop tool moves: a fill window over the source and its
 * keyframes. */
export interface CropTarget {
  /** The window at the playhead, in source pixels. */
  rect: Rect;
  /** The keyframe at the playhead, if any. */
  keyframe?: CropPoint;
  /** Set the window at the playhead to rect (a keyframe there); changes of
   * one gesture undo at once. */
  place: (rect: Rect, gesture: number) => void;
  deleteKeyframe: (key: CropPoint) => void;
  /** Whether there are keyframes or a size to reset, and resetting them. */
  canReset: boolean;
  reset: () => void;
}

/**
 * The crop tool's target at source time t: the keyframes of the scene at
 * the playhead if it is fixed or tracked (scenes.keyed), else the clip's
 * framing (its crop points along the planned window, track).
 */
export function cropTarget(
  edits: ClipEdits,
  scenes: SceneEdits,
  track: CropTrack,
  t: number,
): CropTarget {
  const { framing, crop_offset: offset } = edits.look;
  if (scenes.keyed) {
    const scene = scenes.current;
    return {
      rect: sceneWindowAt(scene, track, framing, offset, t),
      keyframe: keyframeAt(scene, t),
      place: (rect, gesture) =>
        scenes.update(sceneWithRect(scene, rect, t, track), gesture),
      deleteKeyframe: (key) => scenes.update(withoutKeyframe(scene, key.t)),
      canReset: scene.crop_keyframes.length > 0 || scene.scale !== 1,
      reset: () => scenes.update({ ...scene, crop_keyframes: [], scale: 1 }),
    };
  }
  return {
    rect: cropWindowAt(track, framing, offset, t),
    keyframe: pointAt(framing, t),
    place: (rect, gesture) =>
      edits.setLook(
        { framing: framingWithRect(framing, rect, t, track) },
        gesture,
      ),
    deleteKeyframe: (key) =>
      edits.setLook({
        framing: {
          ...framing,
          points: framing.points.filter((point) => point !== key),
        },
      }),
    canReset: framing.points.length > 0 || framing.scale !== 1,
    reset: () =>
      edits.setLook({ framing: { ...framing, scale: 1, points: [] } }),
  };
}
