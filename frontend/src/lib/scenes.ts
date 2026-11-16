/**
 * A clip's scenes (the backend's pipeline/scenes): the spans between the
 * source's scene cuts, each framed on its own: auto (as the clip's crop
 * plan frames it), fixed (at keyframes), tracked, or in the fit or split
 * layout. A clip without stored scenes is framed as its layout says
 * throughout; the editor shows it split at the scene cuts inside it and
 * at the timeline's split points.
 */
import type { Clip, SceneReframe } from "@/api/types";
import type { ClipRange } from "@/lib/timeline";

/** The shortest scene that defaultScenes makes, in seconds. */
export const MIN_SCENE_S = 0.5;
/** Scene edges closer than this (seconds) are one. */
const EDGE_S = 1e-3;

/** How a scene is framed, as the Layout panel offers it. */
export type SceneChoice =
  | "auto"
  | "track"
  | "fixed"
  | "fit"
  | "square_blur"
  | "split"
  | "grid"
  | "pip"
  | "screenshare"
  | "gameplay";

export const SCENE_LABELS: Record<SceneChoice, string> = {
  auto: "Auto",
  track: "Track",
  fixed: "Fixed",
  fit: "Fit",
  square_blur: "Square",
  split: "Split",
  grid: "Grid",
  pip: "Picture in picture",
  screenshare: "Screenshare + facecam",
  gameplay: "Gameplay + facecam",
};

/** How the segment strip names a scene: an auto scene is the fill crop. */
export const SEGMENT_LABELS: Record<SceneChoice, string> = {
  ...SCENE_LABELS,
  auto: "Fill",
};

/** The one-click overrides of the segment strip, in order. */
export const SEGMENT_OVERRIDES: SceneChoice[] = [
  "auto",
  "square_blur",
  "fit",
  "split",
  "track",
];

type Layout = Clip["layout"];

/** A scene from start to end seconds, auto in layout. */
export function autoScene(
  start: number,
  end: number,
  layout: Layout,
): SceneReframe {
  return {
    start,
    end,
    mode: "auto",
    layout,
    crop_keyframes: [],
    scale: 1,
    track_seed: null,
  };
}

const round3 = (value: number) => Math.round(value * 1000) / 1000;

/**
 * The scenes of a clip over range, split at the scene cuts inside it: a
 * cut closer than MIN_SCENE_S to the clip's start, its end or the cut
 * before it is skipped. Each is auto in layout.
 */
export function defaultScenes(
  range: ClipRange,
  cuts: number[],
  layout: Layout,
): SceneReframe[] {
  const bounds = [range.start];
  for (const cut of [...cuts].sort((a, b) => a - b)) {
    const last = bounds[bounds.length - 1];
    if (cut - last >= MIN_SCENE_S && range.end - cut >= MIN_SCENE_S) {
      bounds.push(cut);
    }
  }
  bounds.push(range.end);
  return bounds
    .slice(1)
    .map((end, k) => autoScene(round3(bounds[k]), round3(end), layout));
}

/**
 * scenes fitted to the clip over range: scenes outside it are dropped,
 * the first one left starts at its start and the last ends at its end;
 * none if no scene overlaps it.
 */
export function fitScenes(
  scenes: SceneReframe[],
  range: ClipRange,
): SceneReframe[] {
  const kept = scenes.filter(
    (scene) => scene.end > range.start && scene.start < range.end,
  );
  if (kept.length === 0) return [];
  const fitted = [...kept];
  fitted[0] = { ...fitted[0], start: range.start };
  const last = fitted.length - 1;
  fitted[last] = { ...fitted[last], end: range.end };
  return fitted;
}

/**
 * scenes split at the times splits inside them; both halves keep the
 * scene's framing, and a fixed or tracked scene's keyframes are shared
 * out, each half getting a keyframe at the split where the window is then.
 */
export function splitScenes(
  scenes: SceneReframe[],
  splits: number[],
): SceneReframe[] {
  let result = scenes;
  for (const t of splits) {
    result = result.flatMap((scene) =>
      t - scene.start > EDGE_S && scene.end - t > EDGE_S
        ? splitScene(scene, t)
        : [scene],
    );
  }
  return result;
}

function splitScene(scene: SceneReframe, t: number): SceneReframe[] {
  const keys = scene.crop_keyframes;
  if (keys.length === 0) {
    return [
      { ...scene, end: t },
      { ...scene, start: t },
    ];
  }
  const edge = { t, x: keyValue(keys, "x", t), y: keyValue(keys, "y", t) };
  const before = keys.filter((key) => key.t < t);
  const after = keys.filter((key) => key.t > t);
  return [
    { ...scene, end: t, crop_keyframes: [...before, edge] },
    { ...scene, start: t, crop_keyframes: [edge, ...after] },
  ];
}

/** The x or y of keys (sorted by time) at t: linear between them, held
 * before the first and after the last. */
export function keyValue(
  keys: SceneReframe["crop_keyframes"],
  field: "x" | "y",
  t: number,
): number {
  const k = keys.findIndex((key) => key.t > t);
  if (k === 0) return keys[0][field];
  if (k === -1) return keys[keys.length - 1][field];
  const [a, b] = [keys[k - 1], keys[k]];
  return a[field] + ((b[field] - a[field]) * (t - a.t)) / (b.t - a.t);
}

/** The index of the scene that holds source time t (the first before
 * it, the last after it). */
export function sceneIndexAt(scenes: SceneReframe[], t: number): number {
  const index = scenes.findIndex((scene) => t < scene.end);
  return index === -1 ? scenes.length - 1 : index;
}

/** How scene is framed, as the Layout panel shows it. */
export function sceneChoice(scene: SceneReframe): SceneChoice {
  return scene.layout === "fill" ? scene.mode : scene.layout;
}

/** scene framed as choice; its keyframes stay for a later fixed or track. */
export function withChoice(
  scene: SceneReframe,
  choice: SceneChoice,
): SceneReframe {
  if (choice === "auto" || choice === "track" || choice === "fixed") {
    return { ...scene, layout: "fill", mode: choice };
  }
  return { ...scene, layout: choice, mode: "auto" };
}

/**
 * The scenes to store for scenes: none, with the clip's layout, if every
 * scene is auto in the same layout (the clip as its layout frames it;
 * keyframes of auto scenes are unused); else scenes themselves.
 */
export function compactScenes(
  scenes: SceneReframe[],
  layout: Layout,
): { scenes: SceneReframe[]; layout: Layout } {
  if (scenes.length === 0) return { scenes, layout };
  const first = scenes[0];
  const plain = scenes.every(
    (scene) => scene.mode === "auto" && scene.layout === first.layout,
  );
  return plain ? { scenes: [], layout: first.layout } : { scenes, layout };
}
