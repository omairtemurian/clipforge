import type { SearchHit } from "@/api/types";

/** The clip lengths the Library offers for a clip made from a moment. */
export const MOMENT_LENGTHS = [15, 30, 60, 90] as const;
export const DEFAULT_MOMENT_LENGTH = 30;
/** The longest collection name the API takes (models.COLLECTION_NAME_MAX). */
export const COLLECTION_NAME_MAX = 100;

/** One run of a hit's text, marked if it matched the search. */
export interface TextPart {
  text: string;
  marked: boolean;
}

/** A stable key of a search hit (a project's segment). */
export function hitKey(hit: Pick<SearchHit, "project_id" | "segment_id">) {
  return `${hit.project_id}:${hit.segment_id}`;
}

/**
 * Split a hit's text into plain and marked runs at its highlights (sorted,
 * overlaps merged, clamped to the text).
 */
export function highlightParts(
  text: string,
  highlights: { start: number; end: number }[],
): TextPart[] {
  const spans = [...highlights]
    .map(({ start, end }) => ({
      start: Math.max(0, Math.min(start, text.length)),
      end: Math.max(0, Math.min(end, text.length)),
    }))
    .filter(({ start, end }) => end > start)
    .sort((a, b) => a.start - b.start);
  const parts: TextPart[] = [];
  let at = 0;
  for (const { start, end } of spans) {
    if (end <= at) continue;
    const from = Math.max(start, at);
    const last = parts.at(-1);
    if (from > at) parts.push({ text: text.slice(at, from), marked: false });
    else if (last?.marked) {
      last.text += text.slice(from, end);
      at = end;
      continue;
    }
    parts.push({ text: text.slice(from, end), marked: true });
    at = end;
  }
  if (at < text.length) parts.push({ text: text.slice(at), marked: false });
  return parts;
}

/** The default name of a collection made from the results of query. */
export function resultsCollectionName(query: string): string {
  const words = query.trim();
  return words ? `Moments: ${words}`.slice(0, COLLECTION_NAME_MAX) : "Moments";
}
