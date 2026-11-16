import { describe, expect, it } from "vitest";
import { nearestTarget, snapSpan, snapTargets, snapTime } from "@/lib/snap";

describe("snap targets", () => {
  it("joins words, segment edges, the playhead and layers, sorted once", () => {
    const targets = snapTargets({
      words: [1.2, 1.6, 2],
      segments: [0, 2, 10],
      playhead: 4.5,
      layers: [3, 1.6],
    });
    expect(targets).toEqual([0, 1.2, 1.6, 2, 3, 4.5, 10]);
  });

  it("has no playhead target when there is none, and none when off", () => {
    expect(snapTargets({ words: [1], segments: [], layers: [] })).toEqual([1]);
    expect(
      snapTargets(
        { words: [1], segments: [2], playhead: 3, layers: [4] },
        false,
      ),
    ).toEqual([]);
  });
});

describe("nearest target", () => {
  const targets = [1, 2, 5];

  it("is the closest target within the tolerance", () => {
    expect(nearestTarget(1.9, targets, 0.5)).toBe(2);
    expect(nearestTarget(1.4, targets, 0.5)).toBe(1);
    expect(nearestTarget(4.6, targets, 0.5)).toBe(5);
  });

  it("is null when none is close enough or the tolerance is 0", () => {
    expect(nearestTarget(3.5, targets, 0.5)).toBeNull();
    expect(nearestTarget(2, targets, 0)).toBeNull();
    expect(nearestTarget(2, [], 1)).toBeNull();
  });

  it("takes the earlier target of a tie", () => {
    expect(nearestTarget(1.5, targets, 0.5)).toBe(1);
  });
});

describe("snap time", () => {
  it("moves onto a close target, else keeps the time", () => {
    expect(snapTime(4.8, [5], 0.3)).toBe(5);
    expect(snapTime(4.6, [5], 0.3)).toBe(4.6);
  });
});

describe("snap span", () => {
  it("shifts the span so its start lands on a target, length kept", () => {
    expect(snapSpan({ start: 2.2, end: 4.2 }, [2], 0.3)).toEqual({
      start: 2,
      end: 4,
    });
  });

  it("shifts the span so its end lands on a target", () => {
    const span = snapSpan({ start: 1.1, end: 3.1 }, [3.3], 0.3);
    expect(span.start).toBeCloseTo(1.3);
    expect(span.end).toBeCloseTo(3.3);
  });

  it("uses whichever edge is nearer its target", () => {
    const span = snapSpan({ start: 2.2, end: 4.05 }, [2, 4], 0.3);
    expect(span.start).toBeCloseTo(2.15);
    expect(span.end).toBeCloseTo(4);
  });

  it("keeps the span when no edge is near a target", () => {
    expect(snapSpan({ start: 2.5, end: 3.5 }, [1, 5], 0.3)).toEqual({
      start: 2.5,
      end: 3.5,
    });
  });
});
