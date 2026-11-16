import { describe, expect, it } from "vitest";
import type { TrackItem } from "@/api/types";
import {
  dragSpan,
  itemLabel,
  layerEdges,
  moveSpan,
  placeItem,
  safeLength,
  trimSpan,
  type LayerTracks,
} from "@/lib/layers";

function item(
  id: string,
  start: number,
  end: number,
  rest: Partial<TrackItem> = {},
): TrackItem {
  return {
    id,
    kind: "text",
    asset_id: null,
    start,
    end,
    props: { text: id },
    ...rest,
  };
}

const LAYERS: LayerTracks = {
  broll: [item("b", 1, 3, { kind: "image", asset_id: 4, props: {} })],
  overlays: [],
  text: [item("t", 5, 7)],
  music: [],
  sfx: [item("s", 9, 9.5, { kind: "audio", asset_id: 2, props: {} })],
  voiceover: [],
};

describe("layer items", () => {
  it("label text items by their text and others by kind and asset", () => {
    expect(itemLabel(LAYERS.text[0])).toBe("t");
    expect(itemLabel(LAYERS.broll[0])).toBe("Image #4");
    expect(itemLabel(LAYERS.sfx[0])).toBe("Audio #2");
    expect(itemLabel(item("x", 0, 1, { props: {} }))).toBe("Text");
  });

  it("lists the edges of every item but the excluded one", () => {
    expect(layerEdges(LAYERS)).toEqual([1, 3, 5, 7, 9, 9.5]);
    expect(layerEdges(LAYERS, "t")).toEqual([1, 3, 9, 9.5]);
  });

  it("places an item at a new span, the others unchanged", () => {
    const moved = placeItem(LAYERS.text, "t", { start: 1, end: 3 });
    expect(moved[0]).toMatchObject({ id: "t", start: 1, end: 3 });
    expect(placeItem(LAYERS.text, "zzz", { start: 1, end: 3 })).toEqual(
      LAYERS.text,
    );
  });

  it("leaves a frame per cut part off the clip's length", () => {
    expect(safeLength(20, 0)).toBe(20);
    expect(safeLength(20, 3)).toBeCloseTo(19.9);
  });
});

describe("moving and trimming", () => {
  it("moves a span inside the clip, length kept", () => {
    expect(moveSpan({ start: 2, end: 4 }, 5, 20)).toEqual({ start: 5, end: 7 });
    expect(moveSpan({ start: 2, end: 4 }, -3, 20)).toEqual({
      start: 0,
      end: 2,
    });
    expect(moveSpan({ start: 2, end: 4 }, 19, 20)).toEqual({
      start: 18,
      end: 20,
    });
  });

  it("trims an edge, keeping the shortest length and the clip's ends", () => {
    expect(trimSpan({ start: 2, end: 4 }, "start", 1, 20)).toEqual({
      start: 1,
      end: 4,
    });
    expect(trimSpan({ start: 2, end: 4 }, "start", 5, 20)).toEqual({
      start: 3.9,
      end: 4,
    });
    expect(trimSpan({ start: 2, end: 4 }, "end", 30, 20)).toEqual({
      start: 2,
      end: 20,
    });
    expect(trimSpan({ start: 2, end: 4 }, "end", 0, 20)).toEqual({
      start: 2,
      end: 2.1,
    });
  });
});

describe("dragging an item", () => {
  const span = { start: 2, end: 4 };
  const base = { grab: 0.5, tolerance: 0.3, length: 20 };

  it("moves it with the pointer and snaps its nearer edge", () => {
    expect(
      dragSpan(span, { ...base, drag: "move", pointer: 6.4, targets: [] }),
    ).toEqual({ start: 5.9, end: 7.9 });
    expect(
      dragSpan(span, { ...base, drag: "move", pointer: 6.4, targets: [8] }),
    ).toEqual({ start: 6, end: 8 });
  });

  it("does not snap a move out of the clip", () => {
    expect(
      dragSpan(span, { ...base, drag: "move", pointer: 18.4, targets: [20.1] }),
    ).toEqual({ start: 18, end: 20 });
  });

  it("trims an edge to the pointer, snapped", () => {
    expect(
      dragSpan(span, { ...base, drag: "end", pointer: 5.1, targets: [5.3] }),
    ).toEqual({ start: 2, end: 5.3 });
    expect(
      dragSpan(span, { ...base, drag: "start", pointer: 1.1, targets: [] }),
    ).toEqual({ start: 1.1, end: 4 });
  });
});
