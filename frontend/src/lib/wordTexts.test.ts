import { describe, expect, it } from "vitest";
import type { Word } from "@/api/types";
import { captionText, captionedWords, withWordText } from "./wordTexts";

function word(text: string, start: number, end: number): Word {
  return { text, start, end, speaker: "S0", prob: 0.9, approximate: false };
}

const WORDS = [
  word("Before", 8, 8.5),
  word(" Hello", 10.2, 10.6),
  word("pizza", 10.7, 11.2),
  word("skip", 21, 21.5),
  word("end", 39, 39.5),
  word("After", 41, 41.5),
];

describe("captionedWords", () => {
  it("keeps the words that start in the clip outside its cuts", () => {
    const shown = captionedWords(WORDS, { start: 10, end: 40 }, [[20, 25]]);

    expect(shown.map((item) => item.text)).toEqual([" Hello", "pizza", "end"]);
  });
});

describe("captionText", () => {
  it("is the word's own text, trimmed, without an override", () => {
    expect(captionText(WORDS[1], [])).toBe("Hello");
  });

  it("is the override's text for the word with the same times", () => {
    const overrides = [word("Hallo!", 10.2, 10.6)];

    expect(captionText(WORDS[1], overrides)).toBe("Hallo!");
    expect(captionText(WORDS[2], overrides)).toBe("pizza");
  });

  it("matches times to the millisecond", () => {
    expect(captionText(WORDS[1], [word("Hi", 10.2000004, 10.6)])).toBe("Hi");
  });
});

describe("withWordText", () => {
  it("adds an override with the word's times and speaker", () => {
    expect(withWordText([], WORDS[2], "pizza!")).toEqual([
      { ...WORDS[2], text: "pizza!" },
    ]);
  });

  it("replaces the override of the same word", () => {
    const once = withWordText([], WORDS[2], "pizza!");

    expect(withWordText(once, WORDS[2], "pizza!!")).toEqual([
      { ...WORDS[2], text: "pizza!!" },
    ]);
  });

  it("removes the override when the text is the word's own again", () => {
    const once = withWordText([], WORDS[1], "Hallo");

    expect(withWordText(once, WORDS[1], "Hello")).toEqual([]);
  });

  it("keeps a blank text, which hides the word", () => {
    expect(withWordText([], WORDS[2], "")).toEqual([{ ...WORDS[2], text: "" }]);
  });

  it("keeps spaces as typed", () => {
    expect(withWordText([], WORDS[2], "pizza ")[0].text).toBe("pizza ");
  });
});
