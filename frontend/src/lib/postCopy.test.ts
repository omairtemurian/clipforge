import { describe, expect, it } from "vitest";
import { clipSeconds, currentCopy, withCopy } from "./postCopy";
import type { PostFields } from "./postForm";

const FIELDS: PostFields = {
  title: " Old ",
  caption: "Old text.",
  hashtags: "#old #Old #tags",
  privacy: "unlisted",
};

describe("post copy of the form", () => {
  it("puts the copy in the fields and keeps the privacy", () => {
    expect(
      withCopy(FIELDS, { title: "New", caption: "New text.", hashtags: ["a"] }),
    ).toEqual({
      title: "New",
      caption: "New text.",
      hashtags: "#a",
      privacy: "unlisted",
    });
  });

  it("reads the current text from the fields", () => {
    expect(currentCopy(FIELDS)).toEqual({
      title: "Old",
      caption: "Old text.",
      hashtags: ["old", "tags"],
    });
  });

  it("counts the seconds of the segments less the cuts", () => {
    expect(
      clipSeconds({
        segments: [
          [10, 20],
          [30, 35],
        ],
        cut_ranges: [[12, 14]],
      }),
    ).toBe(13);
  });
});
