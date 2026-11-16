import { describe, expect, it } from "vitest";
import {
  COLLECTION_NAME_MAX,
  highlightParts,
  hitKey,
  resultsCollectionName,
} from "@/lib/library";

describe("highlightParts", () => {
  it("marks the highlighted runs of the text", () => {
    expect(
      highlightParts("we had a funny bit here", [{ start: 9, end: 14 }]),
    ).toEqual([
      { text: "we had a ", marked: false },
      { text: "funny", marked: true },
      { text: " bit here", marked: false },
    ]);
  });

  it("sorts, merges overlaps and clamps to the text", () => {
    expect(
      highlightParts("abcdef", [
        { start: 4, end: 99 },
        { start: 0, end: 2 },
        { start: 1, end: 3 },
        { start: 3, end: 3 },
      ]),
    ).toEqual([
      { text: "abc", marked: true },
      { text: "d", marked: false },
      { text: "ef", marked: true },
    ]);
  });

  it("keeps a text without highlights whole", () => {
    expect(highlightParts("plain", [])).toEqual([
      { text: "plain", marked: false },
    ]);
  });
});

describe("hitKey", () => {
  it("names a project's segment", () => {
    expect(hitKey({ project_id: 3, segment_id: 12 })).toBe("3:12");
  });
});

describe("resultsCollectionName", () => {
  it("names a collection after the query, within the name limit", () => {
    expect(resultsCollectionName(" funny bit ")).toBe("Moments: funny bit");
    expect(resultsCollectionName("")).toBe("Moments");
    expect(resultsCollectionName("x".repeat(300))).toHaveLength(
      COLLECTION_NAME_MAX,
    );
  });
});
