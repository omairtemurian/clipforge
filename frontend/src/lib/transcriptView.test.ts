import { describe, expect, it } from "vitest";
import type { Word } from "@/api/types";
import {
  PAUSE_PILL_S,
  fitText,
  formatPause,
  inRuns,
  pausesBefore,
  searchWords,
  transcriptText,
  wordAt,
} from "./transcriptView";

function word(text: string, start: number, end: number): Word {
  return { text, start, end, speaker: "S0", prob: 0.9, approximate: false };
}

const CLIP = { start: 10, end: 20 };

describe("pausesBefore", () => {
  it("shows a pill for a silence of at least PAUSE_PILL_S", () => {
    const words = [
      word("a", 10, 11),
      word("b", 11 + PAUSE_PILL_S, 12),
      word("c", 12 + PAUSE_PILL_S - 0.01, 13),
      word("d", 14, 15),
    ];
    const pauses = pausesBefore(words, CLIP);
    expect([...pauses.keys()]).toEqual([1, 3]);
    expect(pauses.get(1)).toBeCloseTo(0.3);
    expect(pauses.get(3)).toBeCloseTo(1);
  });

  it("measures the first clip word from the clip's start and skips context", () => {
    const words = [
      word("before", 8, 9.9),
      word("first", 10.5, 11),
      word("after", 21, 22),
    ];
    const pauses = pausesBefore(words, CLIP);
    expect([...pauses.keys()]).toEqual([1]);
    expect(pauses.get(1)).toBeCloseTo(0.5);
  });

  it("formats a pause like 0.96s", () => {
    expect(formatPause(0.9612)).toBe("0.96s");
    expect(formatPause(1.1)).toBe("1.1s");
    expect(formatPause(2.0004)).toBe("2s");
  });
});

describe("searchWords", () => {
  const words = [
    word("Pizza,", 0, 1),
    word("is", 1, 2),
    word("great.", 2, 3),
    word("pizza", 3, 4),
    word("again", 4, 5),
  ];

  it("finds words ignoring case and punctuation", () => {
    expect(searchWords(words, "PIZZA")).toEqual([
      [0, 0],
      [3, 3],
    ]);
    expect(searchWords(words, "gre")).toEqual([[2, 2]]);
  });

  it("finds a phrase as a run of words", () => {
    const runs = searchWords(words, "pizza is");
    expect(runs).toEqual([[0, 1]]);
    expect(inRuns(runs, 1)).toBe(true);
    expect(inRuns(runs, 2)).toBe(false);
  });

  it("finds nothing for an empty query", () => {
    expect(searchWords(words, "  ")).toEqual([]);
    expect(searchWords(words, "!!")).toEqual([]);
  });
});

describe("text helpers", () => {
  it("finds the word spoken at a time", () => {
    const words = [word("a", 1, 2), word("b", 3, 4)];
    expect(wordAt(words, 1.5)).toBe(0);
    expect(wordAt(words, 2.5)).toBe(-1);
    expect(wordAt(words, 3)).toBe(1);
  });

  it("joins words into text", () => {
    expect(transcriptText([word(" Hi", 0, 1), word("there.", 1, 2)])).toBe(
      "Hi there.",
    );
  });

  it("fits text to a limit at a word boundary", () => {
    expect(fitText("one two three", 13)).toBe("one two three");
    expect(fitText("one two three", 10)).toBe("one two");
    expect(fitText("abcdefghij", 4)).toBe("abcd");
  });
});
