import { describe, expect, it } from "vitest";
import type { Waveform } from "@/api/types";
import { filmstripSlots, waveformColumns } from "./timelineMedia";

// 60 tiles, one a second from 0 s, each 16:9.
const STRIP = { start: 0, interval: 1, count: 60, tileAspect: 16 / 9 };

describe("filmstrip slots", () => {
  it("lays tiles side by side, each the frame at its middle", () => {
    // 0-60 s over 640 px: tiles 80 px wide (45 px tall), 7.5 s each.
    const slots = filmstripSlots(STRIP, { start: 0, end: 60 }, 640, 45);
    expect(slots.map((slot) => slot.left)).toEqual([
      0, 80, 160, 240, 320, 400, 480, 560,
    ]);
    expect(slots.map((slot) => slot.index)).toEqual([
      3, 11, 18, 26, 33, 41, 48, 56,
    ]);
  });

  it("zoomed in, neighbouring slots may show the same tile", () => {
    const slots = filmstripSlots(STRIP, { start: 10, end: 12 }, 320, 45);
    expect(slots.map((slot) => slot.index)).toEqual([10, 10, 11, 11]);
  });

  it("clamps to the tiles it has and survives no width", () => {
    const late = filmstripSlots(STRIP, { start: 70, end: 80 }, 80, 45);
    expect(late).toEqual([{ left: 0, index: 59 }]);
    expect(filmstripSlots(STRIP, { start: 0, end: 60 }, 0, 45)).toEqual([]);
  });
});

describe("waveform columns", () => {
  const wave: Waveform = {
    start: 0,
    end: 2,
    peaks_per_second: 2,
    peaks: [0.1, 0.4, 0.2, 0.05],
  };

  it("takes the loudest peak per column, the loudest as 1", () => {
    expect(waveformColumns(wave, { start: 0, end: 2 }, 2)).toEqual([1, 0.5]);
    expect(waveformColumns(wave, { start: 0, end: 2 }, 4)).toEqual([
      0.25, 1, 0.5, 0.125,
    ]);
  });

  it("is silent past the wave and for a silent wave", () => {
    expect(waveformColumns(wave, { start: 2, end: 4 }, 2)).toEqual([0, 0]);
    const silent = { ...wave, peaks: [0, 0, 0, 0] };
    expect(waveformColumns(silent, { start: 0, end: 2 }, 2)).toEqual([0, 0]);
  });
});
