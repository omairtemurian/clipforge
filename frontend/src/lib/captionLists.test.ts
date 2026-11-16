import { describe, expect, it } from "vitest";
import { correctionsText, linesOf, parseCorrections } from "@/lib/captionLists";

describe("caption lists", () => {
  it("reads one entry per line", () => {
    expect(linesOf(" darn \n\nheck*\n")).toEqual(["darn", "heck*"]);
  });

  it("writes and reads corrections, naming bad lines", () => {
    const text = correctionsText({ "clip forge": "ClipForge", gpt: "GPT" });
    expect(text).toBe("clip forge = ClipForge\ngpt = GPT");
    expect(parseCorrections(text)).toEqual({
      corrections: { "clip forge": "ClipForge", gpt: "GPT" },
      bad: [],
    });
    expect(parseCorrections("a = b\n\nno sign\n = c\nd =")).toEqual({
      corrections: { a: "b" },
      bad: [3, 4, 5],
    });
  });
});
