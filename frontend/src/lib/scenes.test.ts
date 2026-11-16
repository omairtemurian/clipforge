import { describe, expect, it } from "vitest";
import type { SceneReframe } from "@/api/types";
import {
  autoScene,
  compactScenes,
  defaultScenes,
  fitScenes,
  keyValue,
  sceneChoice,
  sceneIndexAt,
  splitScenes,
  withChoice,
} from "./scenes";

const key = (t: number, x: number, y = 0.5) => ({ t, x, y });

function fixed(
  start: number,
  end: number,
  keys = [key(12, 0.2), key(16, 0.6)],
) {
  return {
    ...autoScene(start, end, "fill"),
    mode: "fixed",
    crop_keyframes: keys,
  } as SceneReframe;
}

describe("defaultScenes", () => {
  it("splits at the cuts at least 0.5 s from the ends and each other", () => {
    const scenes = defaultScenes(
      { start: 10, end: 20 },
      [19.8, 13.3, 10.2, 13],
      "split",
    );
    expect(scenes.map((s) => [s.start, s.end])).toEqual([
      [10, 13],
      [13, 20],
    ]);
    expect(scenes.every((s) => s.layout === "split" && s.mode === "auto")).toBe(
      true,
    );
  });
});

describe("fitScenes", () => {
  const scenes = [autoScene(10, 13, "fill"), autoScene(13, 20, "fill")];

  it("stretches the outer scenes to the span and drops the rest", () => {
    expect(fitScenes(scenes, { start: 8, end: 12 })).toEqual([
      autoScene(8, 12, "fill"),
    ]);
    expect(fitScenes(scenes, { start: 11, end: 25 })).toEqual([
      autoScene(11, 13, "fill"),
      autoScene(13, 25, "fill"),
    ]);
    expect(fitScenes(scenes, { start: 21, end: 25 })).toEqual([]);
  });
});

describe("splitScenes", () => {
  it("shares out keyframes with one where the window is at the split", () => {
    const [before, after] = splitScenes([fixed(10, 20)], [14]);
    expect(before).toMatchObject({ start: 10, end: 14 });
    expect(before.crop_keyframes).toEqual([key(12, 0.2), key(14, 0.4)]);
    expect(after).toMatchObject({ start: 14, end: 20, mode: "fixed" });
    expect(after.crop_keyframes).toEqual([key(14, 0.4), key(16, 0.6)]);
  });

  it("ignores splits at or outside a scene's edges", () => {
    const scenes = [fixed(10, 20)];
    expect(splitScenes(scenes, [10, 20, 25])).toEqual(scenes);
  });
});

describe("keyValue", () => {
  it("is linear between keyframes and holds outside them", () => {
    const keys = [key(12, 0.2), key(16, 0.6)];
    expect(keyValue(keys, "x", 13)).toBeCloseTo(0.3);
    expect(keyValue(keys, "x", 5)).toBe(0.2);
    expect(keyValue(keys, "x", 30)).toBe(0.6);
  });
});

describe("sceneIndexAt", () => {
  it("finds the scene at a time, clamped to the first and last", () => {
    const scenes = [autoScene(10, 13, "fill"), autoScene(13, 20, "fill")];
    expect(sceneIndexAt(scenes, 9)).toBe(0);
    expect(sceneIndexAt(scenes, 13)).toBe(1);
    expect(sceneIndexAt(scenes, 25)).toBe(1);
  });
});

describe("choices", () => {
  it("maps a choice to a mode and layout, keeping keyframes", () => {
    const fit = withChoice(fixed(10, 20), "fit");
    expect(fit).toMatchObject({ layout: "fit", mode: "auto" });
    expect(fit.crop_keyframes).toHaveLength(2);
    expect(sceneChoice(fit)).toBe("fit");
    const back = withChoice(fit, "fixed");
    expect(sceneChoice(back)).toBe("fixed");
    expect(back.layout).toBe("fill");
  });

  it("frames a scene in the grid, pip and facecam layouts", () => {
    for (const layout of ["grid", "pip", "screenshare", "gameplay"] as const) {
      const scene = withChoice(fixed(10, 20), layout);
      expect(scene).toMatchObject({ layout, mode: "auto" });
      expect(sceneChoice(scene)).toBe(layout);
    }
  });

  it("stores no scenes when all are auto in one layout", () => {
    const auto = [autoScene(10, 13, "fit"), autoScene(13, 20, "fit")];
    expect(compactScenes(auto, "fill")).toEqual({ scenes: [], layout: "fit" });
    const mixed = [auto[0], fixed(13, 20)];
    expect(compactScenes(mixed, "fill")).toEqual({
      scenes: mixed,
      layout: "fill",
    });
    expect(compactScenes([], "split")).toEqual({ scenes: [], layout: "split" });
  });
});
