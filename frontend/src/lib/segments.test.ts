import { describe, expect, it } from "vitest";
import type { Word } from "@/api/types";
import {
  adjacentPoint,
  addSplit,
  canCutSegment,
  segmentAt,
  segments,
  snapToWords,
} from "./segments";

const CLIP = { start: 10, end: 40 };

function word(start: number, end: number): Word {
  return {
    text: "w",
    start,
    end,
    speaker: "S0",
    prob: 0.9,
    approximate: false,
  };
}

describe("split at the playhead", () => {
  it("adds a split inside the clip, sorted", () => {
    expect(addSplit([], 20, CLIP)).toEqual([20]);
    expect(addSplit([30], 15.1234, CLIP)).toEqual([15.123, 30]);
  });

  it("ignores a split outside the clip or next to another edge", () => {
    expect(addSplit([], 10, CLIP)).toEqual([]);
    expect(addSplit([], 45, CLIP)).toEqual([]);
    expect(addSplit([20], 20.05, CLIP)).toEqual([20]);
    expect(addSplit([], 39.95, CLIP)).toEqual([]);
  });

  it("cuts the clip into segments at its splits", () => {
    const splits = addSplit(addSplit([], 20, CLIP), 30, CLIP);
    expect(segments(CLIP, splits, [])).toEqual([
      [10, 20],
      [20, 30],
      [30, 40],
    ]);
  });

  it("leaves cut ranges out as gaps", () => {
    expect(segments(CLIP, [20], [[15, 25]])).toEqual([
      [10, 15],
      [25, 40],
    ]);
    expect(
      segments(
        CLIP,
        [30],
        [
          [12, 14],
          [35, 50],
        ],
      ),
    ).toEqual([
      [10, 12],
      [14, 30],
      [30, 35],
    ]);
    expect(segments(CLIP, [5, 45], [])).toEqual([[10, 40]]);
  });

  it("finds the segment at a time", () => {
    const parts = segments(CLIP, [20], []);
    expect(segmentAt(parts, 20)).toEqual([20, 40]);
    expect(segmentAt(parts, 50)).toBeUndefined();
  });

  it("deletes a segment only if 1 s of clip is left", () => {
    const parts = segments(CLIP, [20], []);
    expect(canCutSegment(parts, [10, 20])).toBe(true);
    expect(canCutSegment([[10, 11.5]], [10, 11.5])).toBe(false);
    expect(
      canCutSegment(
        [
          [10, 11],
          [12, 12.5],
        ],
        [12, 12.5],
      ),
    ).toBe(true);
  });
});

describe("snap to word boundaries", () => {
  const words = [word(10.2, 10.6), word(11, 11.4)];

  it("moves to the nearest word edge within the tolerance", () => {
    expect(snapToWords(10.5, words, 0.5)).toBe(10.6);
    expect(snapToWords(10.75, words, 0.5)).toBe(10.6);
    expect(snapToWords(10.85, words, 0.5)).toBe(11);
  });

  it("keeps the time when no word edge is close enough", () => {
    expect(snapToWords(13, words, 0.5)).toBe(13);
    expect(snapToWords(10.5, [], 0.5)).toBe(10.5);
    expect(snapToWords(10.5, words, 0)).toBe(10.5);
  });
});

describe("skip", () => {
  const points = [10, 40, 20, 25];

  it("goes to the edge before or after the time", () => {
    expect(adjacentPoint(points, 22, -1)).toBe(20);
    expect(adjacentPoint(points, 22, 1)).toBe(25);
    expect(adjacentPoint(points, 20.05, -1)).toBe(10);
    expect(adjacentPoint(points, 40, 1)).toBeUndefined();
  });
});
