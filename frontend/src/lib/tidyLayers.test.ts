import { describe, expect, it } from "vitest";
import type { TrackItem } from "@/api/types";
import type { LayerTracks } from "@/lib/layers";
import { sameLayers, tidyProps } from "./tidyLayers";

const EMPTY: LayerTracks = {
  broll: [],
  overlays: [],
  text: [],
  music: [],
  sfx: [],
  voiceover: [],
};

function item(props: Record<string, unknown>): TrackItem {
  return { id: "a-1", kind: "audio", asset_id: 3, start: 0, end: 2, props };
}

describe("tidyProps", () => {
  it("fills in the backend's defaults and trims a voiceover's text", () => {
    expect(tidyProps("music", item({ volume: 0.5 }))).toEqual({
      volume: 0.5,
      offset: 0,
      fade_in: 0,
      fade_out: 0,
      duck: true,
    });
    expect(tidyProps("voiceover", item({ text: " Hi " })).text).toBe("Hi");
  });
});

describe("sameLayers", () => {
  it("matches layers the backend saves alike, whatever their key order", () => {
    const local = { ...EMPTY, music: [item({ volume: 0.5 })] };
    const saved = {
      ...EMPTY,
      music: [
        item({ duck: true, fade_out: 0, fade_in: 0, offset: 0, volume: 0.5 }),
      ],
    };

    expect(sameLayers(local, saved)).toBe(true);
    expect(sameLayers(local, EMPTY)).toBe(false);
    expect(
      sameLayers(local, { ...EMPTY, music: [item({ volume: 0.6 })] }),
    ).toBe(false);
    expect(
      sameLayers(local, { ...EMPTY, music: [{ ...item({}), end: 3 }] }),
    ).toBe(false);
  });
});
