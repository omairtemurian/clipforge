import type { SettingsUpdate, SettingsView } from "@/api/types";

export type CapField =
  "usage_cap_compute_hours" | "usage_cap_llm_tokens" | "usage_cap_api_calls";

export interface CapRow {
  /** The kind of the usage records (`KindUsage.kind`). */
  kind: string;
  field: CapField;
  label: string;
  /** What the cap is counted in. */
  unit: string;
}

export const CAP_ROWS: CapRow[] = [
  {
    kind: "compute",
    field: "usage_cap_compute_hours",
    label: "Compute time",
    unit: "hours",
  },
  {
    kind: "llm_tokens",
    field: "usage_cap_llm_tokens",
    label: "LLM tokens",
    unit: "tokens",
  },
  {
    kind: "api_calls",
    field: "usage_cap_api_calls",
    label: "Paid API calls",
    unit: "calls",
  },
];

export type CapDraft = Record<CapField, string>;

/** The draft that shows the saved caps (0 = no cap, shown as empty). */
export function capDraftOf(view: SettingsView): CapDraft {
  const text = (value: number) => (value > 0 ? String(value) : "");
  return {
    usage_cap_compute_hours: text(view.usage_cap_compute_hours),
    usage_cap_llm_tokens: text(view.usage_cap_llm_tokens),
    usage_cap_api_calls: text(view.usage_cap_api_calls),
  };
}

/** A typed cap as a number: empty means no cap (0); null if it is not a
 * number of at least 0. */
export function parseCap(text: string): number | null {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  const value = Number(trimmed);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

/** The caps that differ from the saved ones, as a PUT body; null if a typed
 * cap is not valid. */
export function capPatch(
  draft: CapDraft,
  saved: SettingsView,
): SettingsUpdate | null {
  const patch: SettingsUpdate = {};
  for (const { field } of CAP_ROWS) {
    const value = parseCap(draft[field]);
    if (value === null) return null;
    if (value !== saved[field]) patch[field] = value;
  }
  return patch;
}

/** A month's total of a kind for a table: seconds of compute as hours or
 * minutes, the others as counts. */
export function formatUsed(kind: string, units: number): string {
  if (kind === "compute") {
    const hours = units / 3600;
    return hours >= 1
      ? `${hours.toFixed(2)} h`
      : `${(units / 60).toFixed(1)} min`;
  }
  return Math.round(units).toLocaleString("en-US");
}
