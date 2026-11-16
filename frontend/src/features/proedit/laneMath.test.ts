import { describe, expect, it } from "vitest";
import type { EdlItem, ProEditTiming } from "@/api/types";
import {
  dragEdlItem,
  frameTime,
  guideLabel,
  LANES,
  laneItems,
  laneRows,
  nudgeEdlItem,
  snapTargets,
  spanChanged,
  withSpan,
  type SnapTarget,
} from "./laneMath";

const TIMING: ProEditTiming = {
  fps: 30,
  duration: 10,
  words: [
    { text: "why", start: 1.1, end: 1.4 },
    { text: "now", start: 4.02, end: 4.3 },
  ],
  beats: [0.5, 1.0, 1.5, 2.0],
};

function item(
  id: number,
  t_start: number,
  t_end: number,
  kind: EdlItem["kind"] = "zoom_punch",
): EdlItem {
  return {
    id,
    t_start,
    t_end,
    kind,
    params: {},
    reason: "why",
    source: "auto",
  };
}

const NO_SNAP = { targets: [] as SnapTarget[], tolerance: 0 };

describe("lanes", () => {
  it("puts every kind on exactly one lane", () => {
    const kinds = LANES.flatMap((lane) => lane.kinds);
    expect(new Set(kinds).size).toBe(kinds.length);
    expect(kinds).toHaveLength(23);
  });

  it("lists a lane's items in time order", () => {
    const items = [item(1, 3, 4), item(2, 1, 2, "sfx"), item(3, 0.5, 1)];
    expect(laneItems(items, LANES[0]).map((i) => i.id)).toEqual([3, 1]);
  });

  it("stacks overlapping items on rows, touching ones share a row", () => {
    const rows = laneRows([
      item(1, 0, 1, "sfx"),
      item(2, 0.5, 1.5, "sfx"),
      item(3, 1, 2, "sfx"),
      item(4, 1.2, 1.3, "sfx"),
    ]);
    expect(Object.fromEntries(rows)).toEqual({ 1: 0, 2: 1, 3: 0, 4: 2 });
  });
});

describe("snap targets", () => {
  it("are the words, beats, other items' edges and the playhead", () => {
    const targets = snapTargets(TIMING, [item(1, 3, 3.5), item(2, 6, 7)], 1, 8);
    expect(targets.map((t) => [t.t, t.kind])).toEqual([
      [0.5, "beat"],
      [1.0, "beat"],
      [1.1, "word"],
      [1.5, "beat"],
      [2.0, "beat"],
      [4.02, "word"],
      [6, "item"],
      [7, "item"],
      [8, "playhead"],
    ]);
  });

  it("keep one target per time, the word over the beat", () => {
    const timing = { ...TIMING, beats: [1.1] };
    const targets = snapTargets(timing, [], 0);
    expect(targets.filter((t) => t.t === 1.1)).toEqual([
      { t: 1.1, kind: "word", text: "why" },
    ]);
  });
});

describe("dragging an item", () => {
  const zoom = item(1, 3, 3.3);

  it("moves it by its grab, on the frame grid, keeping its length", () => {
    const moved = dragEdlItem(
      zoom,
      { drag: "move", pointer: 5.11, grab: 0.1, ...NO_SNAP },
      TIMING,
    );
    expect(moved.start).toBeCloseTo(frameTime(5.01, 30));
    expect(moved.end - moved.start).toBeCloseTo(0.3);
    expect(moved.guide).toBeNull();
  });

  it("snaps the nearer edge to a beat and says so", () => {
    const targets = snapTargets(TIMING, [], zoom.id);
    const moved = dragEdlItem(
      zoom,
      { drag: "move", pointer: 1.55, grab: 0.1, targets, tolerance: 0.1 },
      TIMING,
    );
    expect(moved.start).toBeCloseTo(1.5);
    expect(moved.end).toBeCloseTo(1.8);
    expect(moved.guide).toEqual({ t: 1.5, kind: "beat" });
    expect(guideLabel(moved.guide!)).toBe("beat");
  });

  it("resizes its end to a word start, then onto a frame", () => {
    const targets = snapTargets(TIMING, [], zoom.id);
    const resized = dragEdlItem(
      zoom,
      { drag: "end", pointer: 4.05, grab: 0, targets, tolerance: 0.1 },
      TIMING,
    );
    expect(resized.start).toBe(3);
    expect(resized.end).toBeCloseTo(frameTime(4.02, 30));
    expect(resized.guide?.kind).toBe("word");
    expect(guideLabel(resized.guide!)).toBe("word “now”");
  });

  it("resizes its start without passing its end", () => {
    const resized = dragEdlItem(
      zoom,
      { drag: "start", pointer: 9, grab: 0, ...NO_SNAP },
      TIMING,
    );
    expect(resized.end).toBe(3.3);
    expect(resized.start).toBeLessThan(resized.end);
    expect(resized.end - resized.start).toBeGreaterThanOrEqual(1 / 30 - 1e-9);
  });

  it("stays inside the clip", () => {
    const late = dragEdlItem(
      zoom,
      { drag: "move", pointer: 30, grab: 0, ...NO_SNAP },
      TIMING,
    );
    const early = dragEdlItem(
      zoom,
      { drag: "move", pointer: -5, grab: 0, ...NO_SNAP },
      TIMING,
    );
    expect(late.end).toBeCloseTo(10);
    expect(late.start).toBeCloseTo(9.7);
    expect(early.start).toBe(0);
    const longer = dragEdlItem(
      zoom,
      { drag: "end", pointer: 12, grab: 0, ...NO_SNAP },
      TIMING,
    );
    expect(longer.end).toBe(10);
  });
});

describe("nudging and editing", () => {
  it("nudges by frames on the grid", () => {
    const span = nudgeEdlItem(item(1, 3, 3.3), 2 / 30, TIMING);
    expect(span.start * 30).toBeCloseTo(92);
    expect(span.end * 30).toBeCloseTo(101);
  });

  it("changes only the edited item, and only when its span moved", () => {
    const items = [item(1, 0, 1), item(2, 2, 3)];
    const edited = withSpan(items, 2, { start: 2.5, end: 3.5 });
    expect(edited[0]).toBe(items[0]);
    expect(edited[1]).toMatchObject({ id: 2, t_start: 2.5, t_end: 3.5 });
    expect(spanChanged(items[1], { start: 2, end: 3 })).toBe(false);
    expect(spanChanged(items[1], { start: 2.5, end: 3.5 })).toBe(true);
  });
});
