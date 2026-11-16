import { describe, expect, it } from "vitest";
import {
  DESCRIPTION_MAX,
  HOOK_MAX,
  TITLE_MAX,
  addHashtags,
  formatHashtags,
  parseHashtags,
  textProblems,
  type TextFields,
} from "./clipText";

const OK: TextFields = {
  title: "Pizza night",
  hook_text: "He ate it all",
  description: "A man and a pizza.",
  hashtags: ["pizza", "funny", "standup"],
};

describe("parseHashtags", () => {
  it("splits on spaces, commas and #, without repeats", () => {
    expect(parseHashtags("#pizza, funny  #Pizza,#stand up")).toEqual([
      "pizza",
      "funny",
      "stand",
      "up",
    ]);
    expect(parseHashtags("  # ,")).toEqual([]);
  });

  it("round-trips with formatHashtags", () => {
    expect(formatHashtags(["a", "b"])).toBe("#a #b");
    expect(parseHashtags(formatHashtags(OK.hashtags))).toEqual(OK.hashtags);
  });
});

describe("textProblems", () => {
  it("accepts texts at the limits", () => {
    expect(
      textProblems({
        title: "t".repeat(TITLE_MAX),
        hook_text: "h".repeat(HOOK_MAX),
        description: "d".repeat(DESCRIPTION_MAX),
        hashtags: ["a", "b", "c", "d", "e", "f", "g", "h"],
      }),
    ).toEqual({});
  });

  it("refuses a title, hook or description one character too long", () => {
    const problems = textProblems({
      ...OK,
      title: "t".repeat(TITLE_MAX + 1),
      hook_text: "h".repeat(HOOK_MAX + 1),
      description: "d".repeat(DESCRIPTION_MAX + 1),
    });
    expect(Object.keys(problems)).toEqual([
      "title",
      "hook_text",
      "description",
    ]);
  });

  it("wants 3 to 8 hashtags", () => {
    expect(textProblems({ ...OK, hashtags: ["a", "b"] }).hashtags).toMatch(
      /3 to 8.*now 2/,
    );
    expect(
      textProblems({
        ...OK,
        hashtags: ["a", "b", "c", "d", "e", "f", "g", "h", "i"],
      }).hashtags,
    ).toMatch(/now 9/);
  });
});

describe("addHashtags", () => {
  it("drops the #, repeats (ignoring case) and the ones over the max", () => {
    expect(addHashtags(["Pizza"], "#pizza #Funny, #fun", 2)).toEqual([
      "Pizza",
      "Funny",
    ]);
  });
});
