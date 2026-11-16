import { describe, expect, it } from "vitest";
import type { Word } from "@/api/types";
import {
  addCut,
  cutAt,
  isCut,
  isSelected,
  mergeCuts,
  restoreCut,
  selectionBounds,
  selectionSpan,
  subtractCuts,
  wordPlace,
} from "./cuts";

function word(text: string, start: number, end: number): Word {
  return { text, start, end, speaker: "S0", prob: 0.9, approximate: false };
}

// "one two three four five" from 10 s, each word 0.5 s with 0.1 s gaps.
const WORDS = ["one", "two", "three", "four", "five"].map((text, i) =>
  word(text, 10 + i * 0.6, 10.5 + i * 0.6),
);
const CLIP = { start: 10, end: 20 };

describe("selection -> cut_ranges", () => {
  it("orders the ends of a selection made either way", () => {
    expect(selectionBounds({ anchor: 3, focus: 1 })).toEqual([1, 3]);
    expect(isSelected({ anchor: 3, focus: 1 }, 2)).toBe(true);
    expect(isSelected({ anchor: 3, focus: 1 }, 4)).toBe(false);
    expect(isSelected(null, 0)).toBe(false);
  });

  it("spans from the first selected word's start to the last one's end", () => {
    expect(selectionSpan(WORDS, { anchor: 1, focus: 1 })).toEqual([10.6, 11.1]);
    expect(selectionSpan(WORDS, { anchor: 3, focus: 1 })).toEqual([10.6, 12.3]);
    expect(selectionSpan([], { anchor: 0, focus: 0 })).toBe(null);
  });

  it("adds a cut, merging it with cuts it overlaps or touches", () => {
    const one = addCut([], [10.6, 11.1], CLIP);
    expect(one).toEqual([[10.6, 11.1]]);
    const apart = addCut(one, [12.4, 12.9], CLIP);
    expect(apart).toEqual([
      [10.6, 11.1],
      [12.4, 12.9],
    ]);
    expect(addCut(apart, [11.0, 12.4], CLIP)).toEqual([[10.6, 12.9]]);
  });

  it("trims a cut to the clip and ignores one outside it", () => {
    expect(addCut([], [8, 10.5], CLIP)).toEqual([[10, 10.5]]);
    const cuts: [number, number][] = [[12, 13]];
    expect(addCut(cuts, [20, 22], CLIP)).toBe(cuts);
  });

  it("merges unsorted overlapping cuts", () => {
    expect(
      mergeCuts([
        [5, 6],
        [1, 2],
        [1.5, 3],
      ]),
    ).toEqual([
      [1, 3],
      [5, 6],
    ]);
  });
});

describe("restore and struck words", () => {
  const cuts: [number, number][] = [
    [10.6, 11.7],
    [12.4, 12.9],
  ];

  it("strikes the words whose middle a cut holds", () => {
    expect(WORDS.map((w) => isCut(w, cuts))).toEqual([
      false,
      true,
      true,
      false,
      true,
    ]);
    expect(isCut(word("edge", 10.4, 10.7), cuts)).toBe(false);
  });

  it("restores the whole cut that removes a time", () => {
    expect(cutAt(cuts, 11)).toEqual([10.6, 11.7]);
    expect(restoreCut(cuts, 11)).toEqual([[12.4, 12.9]]);
    expect(restoreCut(cuts, 12)).toBe(cuts);
  });
});

describe("words around the clip", () => {
  it("places a word by its start", () => {
    expect(wordPlace(word("a", 9.8, 10.2), CLIP)).toBe("before");
    expect(wordPlace(word("b", 10, 10.2), CLIP)).toBe("inside");
    expect(wordPlace(word("c", 19.9, 20.4), CLIP)).toBe("inside");
    expect(wordPlace(word("d", 20, 20.4), CLIP)).toBe("after");
  });
});

describe("subtractCuts", () => {
  it("keeps the parts of each cut outside the removed ranges", () => {
    expect(
      subtractCuts(
        [
          [1, 2],
          [3, 8],
          [9, 10],
        ],
        [
          [5, 6],
          [3, 4],
          [9, 10],
          [7.5, 12],
        ],
      ),
    ).toEqual([
      [1, 2],
      [4, 5],
      [6, 7.5],
    ]);
  });

  it("keeps every cut when nothing is removed", () => {
    expect(subtractCuts([[1, 2]], [])).toEqual([[1, 2]]);
  });
});
