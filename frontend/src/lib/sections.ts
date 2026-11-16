/**
 * The clip's sections (its segments, in play order): moving one to play
 * elsewhere, which part of the source can be added, and where a section
 * or the clip can be split.
 */
import type { Segment } from "@/api/types";
import { MIN_SEGMENT_S } from "@/lib/segments";
import type { CutRange } from "@/lib/timeline";

/** The most transcript segments the add-section picker lists. */
export const PICKER_LIMIT = 50;

/**
 * The sections' indices in play order after the section at play position
 * `from` moves to play at `to` (SectionOrder.order: the API's body);
 * unchanged for an out-of-range move.
 */
export function movedOrder(count: number, from: number, to: number): number[] {
  const order = Array.from({ length: count }, (_, index) => index);
  if (from === to || from < 0 || to < 0 || from >= count || to >= count) {
    return order;
  }
  const [moved] = order.splice(from, 1);
  order.splice(to, 0, moved);
  return order;
}

/** Whether order is not the sections' current play order. */
export function reorders(order: number[]): boolean {
  return order.some((value, index) => value !== index);
}

/** Whether start-end of the source overlaps one of the sections. */
export function overlapsSection(
  sections: CutRange[],
  start: number,
  end: number,
): boolean {
  return sections.some(([from, to]) => start < to && end > from);
}

/**
 * The transcript segments the add-section picker lists: those whose text
 * holds the query (any case; all of them if it is empty), the PICKER_LIMIT
 * nearest to the clip's first section, in source order.
 */
export function pickerSegments(
  segments: Segment[],
  near: number,
  query: string,
): Segment[] {
  const needle = query.trim().toLowerCase();
  const matching = segments.filter(
    (segment) =>
      segment.text.trim() !== "" &&
      segment.end > segment.start &&
      segment.text.toLowerCase().includes(needle),
  );
  return matching
    .map((segment) => ({ segment, gap: Math.abs(segment.start - near) }))
    .sort((a, b) => a.gap - b.gap)
    .slice(0, PICKER_LIMIT)
    .map(({ segment }) => segment)
    .sort((a, b) => a.start - b.start);
}

/**
 * The section that plays source time t with at least MIN_SEGMENT_S on both
 * sides of t (where a split can be made), if there is one.
 */
export function splittableSection(
  sections: CutRange[],
  t: number,
): CutRange | undefined {
  return sections.find(
    ([from, to]) => t - from >= MIN_SEGMENT_S && to - t >= MIN_SEGMENT_S,
  );
}
