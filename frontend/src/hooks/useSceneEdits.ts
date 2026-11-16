import { useClipScenes } from "@/api/clips";
import type { SceneReframe } from "@/api/types";
import type { KeyframeRowProps } from "@/components/editor/TimelineKeyframes";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { keyframeAt, movedKeyframe, withoutKeyframe } from "@/lib/sceneCrop";
import {
  compactScenes,
  defaultScenes,
  keyValue,
  SEGMENT_LABELS,
  sceneChoice,
  sceneIndexAt,
  splitScenes,
  withChoice,
  type SceneChoice,
} from "@/lib/scenes";
import type { CutRange } from "@/lib/timeline";

export interface SceneEdits {
  /** The clip's scenes as the editor shows them, in order. */
  scenes: SceneReframe[];
  /** The scene at the playhead, and its index. */
  index: number;
  current: SceneReframe;
  /** The edges between scenes, in source seconds. */
  bounds: number[];
  /** Whether the scene at the playhead is framed at keyframes (fixed or
   * tracked, in the fill layout). */
  keyed: boolean;
  /** The label of a segment: how the scene it starts in is framed. */
  labelAt: (part: CutRange) => string;
  /** How the scene a segment starts in is framed, and frame it as choice. */
  choiceAt: (part: CutRange) => SceneChoice;
  chooseAt: (part: CutRange, choice: SceneChoice) => void;
  /** The keyframes row of the scene at the playhead, if it is keyed;
   * clicking a keyframe seeks there. */
  keyframeRow: (seek: (t: number) => void) => KeyframeRowProps | undefined;
  /** Frame the scene at the playhead as choice. */
  choose: (choice: SceneChoice) => void;
  /** Frame every scene as the scene at the playhead (see framedAs). */
  applyToAll: () => void;
  /** Replace the scene at the playhead; changes of one gesture undo at once. */
  update: (scene: SceneReframe, gesture?: number) => void;
}

/**
 * scene framed as model: model itself, else in its layout and mode, and
 * if that is keyed, fixed where model's window is at source time t.
 */
function framedAs(
  scene: SceneReframe,
  model: SceneReframe,
  t: number,
): SceneReframe {
  if (scene === model) return model;
  const keys = model.crop_keyframes;
  const keyed = model.layout === "fill" && model.mode !== "auto";
  const hold =
    keyed && keys.length > 0
      ? [
          {
            t: scene.start,
            x: keyValue(keys, "x", t),
            y: keyValue(keys, "y", t),
          },
        ]
      : [];
  return {
    ...scene,
    layout: model.layout,
    mode: keyed ? "fixed" : "auto",
    scale: model.scale,
    crop_keyframes: hold,
    track_seed: null,
  };
}

/**
 * The scenes of the clip being edited (lib/scenes): its stored scenes, or
 * the clip split at its source's scene cuts (GET /clips/{id}/scenes; none
 * if that fails), split again at the timeline's split points. Changing one
 * stores them all, or none if they all frame the clip as its layout does.
 */
export function useSceneEdits(
  clipId: number,
  edits: ClipEdits,
  playhead: number,
): SceneEdits {
  const cuts = useClipScenes(clipId).data?.cuts ?? [];
  const { range, look } = edits;
  const base =
    edits.scenes.length > 0
      ? edits.scenes
      : defaultScenes(range, cuts, look.layout);
  const scenes = splitScenes(base, edits.splits);
  const index = sceneIndexAt(scenes, playhead);
  const current = scenes[index];
  const keyed = current.layout === "fill" && current.mode !== "auto";

  const store = (next: SceneReframe[], gesture?: number) => {
    const compact = compactScenes(next, look.layout);
    edits.setScenes(compact.scenes, compact.layout, gesture);
  };
  const replaceAt = (at: number, scene: SceneReframe, gesture?: number) =>
    store(
      scenes.map((s, k) => (k === at ? scene : s)),
      gesture,
    );
  const replace = (scene: SceneReframe, gesture?: number) =>
    replaceAt(index, scene, gesture);
  const sceneOf = (part: CutRange) => sceneIndexAt(scenes, part[0]);

  return {
    scenes,
    index,
    current,
    bounds: scenes.slice(1).map((scene) => scene.start),
    keyed,
    labelAt: (part) => SEGMENT_LABELS[sceneChoice(scenes[sceneOf(part)])],
    choiceAt: (part) => sceneChoice(scenes[sceneOf(part)]),
    chooseAt: (part, choice) =>
      replaceAt(sceneOf(part), withChoice(scenes[sceneOf(part)], choice)),
    keyframeRow: (seek) =>
      keyed
        ? {
            scene: { start: current.start, end: current.end },
            keys: current.crop_keyframes,
            current: keyframeAt(current, playhead)?.t,
            onSeek: seek,
            onMove: (from, to, gesture) =>
              replace(movedKeyframe(current, from, to), gesture),
            onDelete: (t) => replace(withoutKeyframe(current, t)),
          }
        : undefined,
    choose: (choice) => replace(withChoice(current, choice)),
    applyToAll: () => store(scenes.map((s) => framedAs(s, current, playhead))),
    update: replace,
  };
}
