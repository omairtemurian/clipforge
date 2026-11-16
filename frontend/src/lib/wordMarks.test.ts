import { describe, expect, it } from "vitest";
import type { CaptionMark, Word } from "@/api/types";
import {
  isEmoji,
  isMarked,
  markFields,
  markOf,
  speakersOf,
  withMark,
  withoutUserMark,
} from "@/lib/wordMarks";

function word(text: string, start: number, speaker = "S0"): Word {
  return {
    text,
    start,
    end: start + 0.3,
    speaker,
    prob: 1,
    approximate: false,
  };
}

function mark(start: number, fields: Partial<CaptionMark>): CaptionMark {
  return {
    start,
    emphasis: null,
    emoji: null,
    censor: null,
    color: null,
    source: "user",
    ...fields,
  };
}

const PIZZA = word("pizza", 10.7);

describe("word marks", () => {
  it("takes the editor's mark over the AI's, matched to the millisecond", () => {
    const ai = mark(10.7004, { emoji: "🍕", source: "ai" });
    const user = mark(10.7, { emphasis: true });
    expect(markOf([ai], PIZZA)).toBe(ai);
    expect(markOf([user, ai], PIZZA)).toBe(user);
    expect(markOf([mark(10.71, {})], PIZZA)).toBeUndefined();
    expect(markFields(null, PIZZA)).toEqual({
      emphasis: null,
      emoji: null,
      censor: null,
      color: null,
    });
  });

  it("changes a word's mark starting from the one that applies", () => {
    const ai = mark(10.7, { emoji: "🍕", emphasis: true, source: "ai" });
    const marks = withMark([ai], PIZZA, { color: "#00ff00" });
    expect(marks).toEqual([
      ai,
      mark(10.7, { emoji: "🍕", emphasis: true, color: "#00ff00" }),
    ]);
    expect(withMark(marks, PIZZA, { censor: true }).at(-1)).toEqual(
      mark(10.7, {
        emoji: "🍕",
        emphasis: true,
        color: "#00ff00",
        censor: true,
      }),
    );
  });

  it("drops an empty mark unless it must beat an AI mark", () => {
    const set = withMark([], PIZZA, { emoji: "🔥" });
    expect(isMarked(set, PIZZA)).toBe(true);
    expect(withMark(set, PIZZA, { emoji: null })).toEqual([]);

    const ai = mark(10.7, { emoji: "🍕", source: "ai" });
    expect(withMark([ai], PIZZA, { emoji: null })).toEqual([
      ai,
      mark(10.7, {}),
    ]);
    expect(withoutUserMark([ai, mark(10.7, {})], PIZZA)).toEqual([ai]);
  });

  it("knows the emojis the backend takes", () => {
    expect(isEmoji("🔥")).toBe(true);
    expect(isEmoji("❤️")).toBe(true);
    expect(isEmoji("a")).toBe(false);
    expect(isEmoji("🔥🔥")).toBe(false);
    expect(isEmoji("")).toBe(false);
  });

  it("lists the known speakers in order", () => {
    expect(
      speakersOf([
        word("a", 1, "S1"),
        word("b", 2, ""),
        word("c", 3, "S0"),
        word("d", 4, "S1"),
      ]),
    ).toEqual(["S1", "S0"]);
  });
});
