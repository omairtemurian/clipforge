import { describe, expect, it } from "vitest";
import type { TrackItem } from "@/api/types";
import type { LayerTracks } from "@/lib/layers";
import { copyId, findItem, pastedItem, removeItem } from "./layerItems";

function item(id: string, start: number, end: number): TrackItem {
  return { id, kind: "text", asset_id: null, start, end, props: { text: id } };
}

const LAYERS: LayerTracks = {
  broll: [],
  overlays: [],
  text: [item("t1", 1, 3), item("t1-copy", 4, 5)],
  music: [item("m1", 0, 10)],
  sfx: [],
  voiceover: [],
};

describe("layer items", () => {
  it("finds an item and its track by id", () => {
    expect(findItem(LAYERS, "m1")).toEqual({
      name: "music",
      item: LAYERS.music[0],
    });
    expect(findItem(LAYERS, "nope")).toBeNull();
    expect(findItem(LAYERS, null)).toBeNull();
  });

  it("removes an item", () => {
    expect(removeItem(LAYERS.text, "t1")).toEqual([LAYERS.text[1]]);
  });

  it("makes copy ids no item has", () => {
    expect(copyId(LAYERS, "m1")).toBe("m1-copy");
    expect(copyId(LAYERS, "t1")).toBe("t1-copy-2");
    expect(copyId(LAYERS, "t1-copy")).toBe("t1-copy-2");
  });

  it("pastes a copy at a time, kept inside the clip", () => {
    const pasted = pastedItem(LAYERS, LAYERS.text[0], 7, 20);
    expect(pasted).toEqual({
      ...LAYERS.text[0],
      id: "t1-copy-2",
      start: 7,
      end: 9,
    });
    expect(pasted.props).not.toBe(LAYERS.text[0].props);
    expect(pastedItem(LAYERS, LAYERS.text[0], 19.5, 20)).toMatchObject({
      start: 18,
      end: 20,
    });
    expect(pastedItem(LAYERS, LAYERS.music[0], 0, 4)).toMatchObject({
      start: 0,
      end: 4,
    });
  });
});
