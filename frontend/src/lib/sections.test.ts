import { describe, expect, it } from "vitest";
import type { Segment } from "@/api/types";
import {
  PICKER_LIMIT,
  movedOrder,
  overlapsSection,
  pickerSegments,
  reorders,
  splittableSection,
} from "./sections";

function segment(id: number, start: number, text: string): Segment {
  return { id, start, end: start + 2, text, words: [], speaker: "S0" };
}

describe("movedOrder", () => {
  it("moves a section to play elsewhere", () => {
    expect(movedOrder(4, 0, 2)).toEqual([1, 2, 0, 3]);
    expect(movedOrder(4, 3, 0)).toEqual([3, 0, 1, 2]);
  });

  it("leaves the order for a move to the same place or out of range", () => {
    expect(movedOrder(3, 1, 1)).toEqual([0, 1, 2]);
    expect(movedOrder(3, 1, 5)).toEqual([0, 1, 2]);
    expect(movedOrder(3, -1, 0)).toEqual([0, 1, 2]);
  });

  it("tells a changed order from the current one", () => {
    expect(reorders([0, 1, 2])).toBe(false);
    expect(reorders([1, 0, 2])).toBe(true);
  });
});

describe("overlapsSection", () => {
  const sections: [number, number][] = [
    [10, 20],
    [30, 40],
  ];

  it("is true for a span that shares time with a section", () => {
    expect(overlapsSection(sections, 18, 22)).toBe(true);
    expect(overlapsSection(sections, 12, 14)).toBe(true);
  });

  it("is false for a span between or touching sections", () => {
    expect(overlapsSection(sections, 20, 30)).toBe(false);
    expect(overlapsSection(sections, 0, 10)).toBe(false);
  });
});

describe("pickerSegments", () => {
  const all = [
    segment(0, 0, "Hello there"),
    segment(1, 10, "Pizza time"),
    segment(2, 20, "Another PIZZA"),
    segment(3, 30, "  "),
  ];

  it("lists the segments with text in source order", () => {
    expect(pickerSegments(all, 0, "").map((s) => s.id)).toEqual([0, 1, 2]);
  });

  it("filters by the query in any case", () => {
    expect(pickerSegments(all, 0, " pizza ").map((s) => s.id)).toEqual([1, 2]);
  });

  it("keeps the ones nearest to the clip when there are too many", () => {
    const many = Array.from({ length: 200 }, (_, i) => segment(i, i * 3, "x"));

    const listed = pickerSegments(many, 300, "");

    expect(listed).toHaveLength(PICKER_LIMIT);
    expect(listed[0].start).toBeGreaterThan(150);
    expect(listed[PICKER_LIMIT - 1].start).toBeLessThan(450);
    expect(listed.map((s) => s.start)).toEqual(
      [...listed.map((s) => s.start)].sort((a, b) => a - b),
    );
  });
});

describe("splittableSection", () => {
  const sections: [number, number][] = [
    [10, 20],
    [30, 40],
  ];

  it("finds the section a time is well inside", () => {
    expect(splittableSection(sections, 35)).toEqual([30, 40]);
  });

  it("finds none at an edge or in a gap", () => {
    expect(splittableSection(sections, 10)).toBeUndefined();
    expect(splittableSection(sections, 25)).toBeUndefined();
    expect(splittableSection(sections, 39.95)).toBeUndefined();
  });
});
