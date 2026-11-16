import { describe, expect, it } from "vitest";
import { clip, scored } from "@/testing/mockApi";
import { clipLength, isEdited, scoreTone, visibleClips } from "./clips";

const ALL = { sort: "score", minScore: 0, query: "" } as const;

describe("scoreTone", () => {
  it.each([
    [59, "low"],
    [60, "medium"],
    [79, "medium"],
    [80, "high"],
    [99, "high"],
    [0, "low"],
  ])("%i is %s", (score, tone) => {
    expect(scoreTone(score)).toBe(tone);
  });
});

describe("clipLength / isEdited", () => {
  it("leaves out the cut ranges", () => {
    const cut = clip({ start: 10, end: 40, cut_ranges: [[12, 14.5]] });
    expect(clipLength(cut)).toBe(27.5);
    expect(clipLength(clip({ start: 10, end: 40 }))).toBe(30);
  });

  it("is edited with cuts or reworded captions only", () => {
    expect(isEdited(clip())).toBe(false);
    expect(isEdited(clip({ cut_ranges: [[11, 12]] }))).toBe(true);
    expect(
      isEdited(
        clip({
          caption_overrides: [
            {
              text: "hi",
              start: 10,
              end: 11,
              speaker: "",
              prob: 1,
              approximate: false,
            },
          ],
        }),
      ),
    ).toBe(true);
  });
});

describe("visibleClips", () => {
  const clips = [
    scored(1, 70, "Yoga"),
    scored(2, 95, "Pizza"),
    { ...scored(3, 95, "Fridge"), hashtags: ["StandUp"] },
    { ...scored(4, 50, "Short one"), end: 15, hook_text: "Wait for it" },
    { ...scored(5, 40, "Last"), description: "The whole pizza." },
  ];
  const ids = (list: ReturnType<typeof visibleClips>) => list.map((c) => c.id);

  it("sorts best score first, ties by id", () => {
    expect(ids(visibleClips(clips, ALL))).toEqual([2, 3, 1, 4, 5]);
  });

  it("sorts shortest first", () => {
    expect(ids(visibleClips(clips, { ...ALL, sort: "duration" }))).toEqual([
      4, 1, 2, 3, 5,
    ]);
  });

  it("keeps the clips at or above the minimum score", () => {
    expect(ids(visibleClips(clips, { ...ALL, minScore: 70 }))).toEqual([
      2, 3, 1,
    ]);
  });

  it("searches title, hook, description and hashtags ignoring case", () => {
    const found = (query: string) =>
      ids(visibleClips(clips, { ...ALL, query }));
    expect(found("  PIZZA ")).toEqual([2, 5]);
    expect(found("whole pizza")).toEqual([5]);
    expect(found("wait for")).toEqual([4]);
    expect(found("standup")).toEqual([3]);
    expect(found("nothing")).toEqual([]);
  });

  it("does not change the list it gets", () => {
    const before = ids(clips);
    visibleClips(clips, ALL);
    expect(ids(clips)).toEqual(before);
  });
});
