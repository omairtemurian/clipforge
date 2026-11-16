import type { EdlItem, ProEditPlan } from "@/api/types";
import { formatTimecode } from "@/lib/format";
import { KIND_LABELS } from "./laneMath";

export interface ItemChange {
  op: "added" | "removed" | "changed";
  itemId: number;
  /** E.g. "Zoom punch". */
  label: string;
  /** What differs for a changed item, e.g. "scale 1.2 → 1.3". */
  details: string[];
}

const show = (value: unknown) =>
  value === undefined
    ? "unset"
    : typeof value === "string"
      ? value
      : JSON.stringify(value);

/** What differs between the two versions of one item. */
function detailsOf(before: EdlItem, after: EdlItem): string[] {
  const details: string[] = [];
  if (before.kind !== after.kind) {
    details.push(`${KIND_LABELS[before.kind]} → ${KIND_LABELS[after.kind]}`);
  }
  if (before.t_start !== after.t_start || before.t_end !== after.t_end) {
    details.push(
      `${formatTimecode(before.t_start)}–${formatTimecode(before.t_end)} → ` +
        `${formatTimecode(after.t_start)}–${formatTimecode(after.t_end)}`,
    );
  }
  const keys = new Set([
    ...Object.keys(before.params),
    ...Object.keys(after.params),
  ]);
  for (const key of keys) {
    const was = before.params[key];
    const now = after.params[key];
    if (JSON.stringify(was) !== JSON.stringify(now)) {
      details.push(`${key} ${show(was)} → ${show(now)}`);
    }
  }
  return details;
}

/**
 * The difference of two plan versions by item id: items only in `after`
 * were added, items only in `before` removed, the others changed when
 * their kind, times or params differ (a changed reason alone is not).
 */
export function diffPlans(
  before: ProEditPlan,
  after: ProEditPlan,
): ItemChange[] {
  const was = new Map(before.items.map((item) => [item.id, item]));
  const now = new Map(after.items.map((item) => [item.id, item]));
  const changes: ItemChange[] = [];
  for (const item of after.items) {
    const old = was.get(item.id);
    if (!old) {
      changes.push({
        op: "added",
        itemId: item.id,
        label: KIND_LABELS[item.kind],
        details: [],
      });
      continue;
    }
    const details = detailsOf(old, item);
    if (details.length > 0) {
      changes.push({
        op: "changed",
        itemId: item.id,
        label: KIND_LABELS[item.kind],
        details,
      });
    }
  }
  for (const item of before.items) {
    if (!now.has(item.id)) {
      changes.push({
        op: "removed",
        itemId: item.id,
        label: KIND_LABELS[item.kind],
        details: [],
      });
    }
  }
  return changes;
}
