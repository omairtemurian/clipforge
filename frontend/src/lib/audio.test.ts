import { describe, expect, it } from "vitest";
import type { TrackItem } from "@/api/types";
import {
  chooseMusic,
  currentMusic,
  musicProps,
  patchProps,
  percent,
} from "@/lib/audio";
import type { LayerTracks } from "@/lib/layers";

const EMPTY: LayerTracks = {
  broll: [],
  overlays: [],
  text: [],
  music: [],
  sfx: [],
  voiceover: [],
};

const item = (id: string, assetId: number, props = {}): TrackItem => ({
  id,
  kind: "audio",
  asset_id: assetId,
  start: 1,
  end: 9,
  props,
});

describe("chooseMusic", () => {
  it("puts a new item over the whole clip with the defaults", () => {
    const items = chooseMusic(EMPTY, undefined, 5, 12.3456);
    expect(items).toEqual([
      {
        id: "music-1",
        kind: "audio",
        asset_id: 5,
        start: 0,
        end: 12.345,
        props: {
          volume: 0.5,
          offset: 0,
          fade_in: 1,
          fade_out: 1,
          duck: true,
        },
      },
    ]);
  });

  it("swaps the asset of the current item and keeps the rest", () => {
    const current = item("music-1", 5, { volume: 0.8 });
    const items = chooseMusic({ ...EMPTY, music: [current] }, current, 6, 30);
    expect(items).toEqual([{ ...current, asset_id: 6 }]);
  });

  it("gives nothing for a clip that is too short", () => {
    expect(chooseMusic(EMPTY, undefined, 5, 0.05)).toBeNull();
  });
});

describe("currentMusic", () => {
  const layers = {
    ...EMPTY,
    music: [item("music-1", 1), item("music-2", 2)],
  };
  it("is the selected music item, else the first", () => {
    expect(currentMusic(layers, "music-2")?.id).toBe("music-2");
    expect(currentMusic(layers, "sfx-1")?.id).toBe("music-1");
    expect(currentMusic(EMPTY, null)).toBeUndefined();
  });
});

describe("props", () => {
  it("fills in defaults", () => {
    expect(musicProps(item("m", 1, { volume: 0.2 }))).toMatchObject({
      volume: 0.2,
      fade_in: 1,
      duck: true,
    });
  });

  it("changes one item's props", () => {
    const items = [item("a", 1, { volume: 1 }), item("b", 2, { volume: 1 })];
    expect(patchProps(items, "b", { duck: false })[1].props).toEqual({
      volume: 1,
      duck: false,
    });
    expect(patchProps(items, "b", { duck: false })[0]).toBe(items[0]);
  });

  it("formats levels", () => {
    expect(percent(0.55)).toBe("55%");
  });
});
