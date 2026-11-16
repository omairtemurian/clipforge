/**
 * What the transcript editor shows about the words of a clip: the pauses
 * between them, the words a search finds and the word being played.
 */
import type { Word } from "@/api/types";
import type { ClipRange } from "@/lib/timeline";

/** A silence between words at least this long (seconds) shows as a pill. */
export const PAUSE_PILL_S = 0.3;

/** A run of word indices from first to last, both included. */
export type WordRun = [number, number];

/**
 * The pause before each word of the clip that has one: the silence from the
 * end of the word before it (or the clip's start, if later) to its start,
 * when at least PAUSE_PILL_S long. Keys are word indices; values seconds.
 */
export function pausesBefore(
  words: Word[],
  clip: ClipRange,
): Map<number, number> {
  const pauses = new Map<number, number>();
  words.forEach((word, index) => {
    if (word.start < clip.start || word.start >= clip.end) return;
    const previous = index > 0 ? words[index - 1].end : clip.start;
    const gap = word.start - Math.max(previous, clip.start);
    if (gap >= PAUSE_PILL_S - 1e-9) pauses.set(index, gap);
  });
  return pauses;
}

/** A pause's length as a pill shows it: "0.96s", "1.1s", "2s". */
export function formatPause(seconds: number): string {
  return `${Number(seconds.toFixed(2))}s`;
}

/** Lowercase text without punctuation, for matching words. */
function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}'\s]/gu, "")
    .trim();
}

/**
 * The runs of words that query matches, in order: each query word must be
 * part of the next transcript word (ignoring case and punctuation), so
 * "pizza is" finds "pizza" followed by "is". An empty query finds nothing.
 */
export function searchWords(words: Word[], query: string): WordRun[] {
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  if (terms.length === 0) return [];
  const texts = words.map((word) => normalize(word.text));
  const runs: WordRun[] = [];
  for (let first = 0; first + terms.length <= texts.length; first++) {
    if (terms.every((term, k) => texts[first + k].includes(term))) {
      runs.push([first, first + terms.length - 1]);
    }
  }
  return runs;
}

/** Whether word index lies in one of runs. */
export function inRuns(runs: WordRun[], index: number): boolean {
  return runs.some(([first, last]) => index >= first && index <= last);
}

/** The index of the word spoken at source time t, or -1 if none is. */
export function wordAt(words: Word[], t: number): number {
  return words.findIndex((word) => t >= word.start && t < word.end);
}

/** The text of the clip's words that no cut removes, for a download. */
export function transcriptText(words: Word[]): string {
  return words
    .map((word) => word.text.trim())
    .filter(Boolean)
    .join(" ");
}

/** text cut to at most max characters, at a word boundary when it has to
 * be cut (a single longer word is cut mid-word). */
export function fitText(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max + 1);
  const space = cut.lastIndexOf(" ");
  return (space > 0 ? cut.slice(0, space) : clean.slice(0, max)).trim();
}

/** The longest title and hook text a clip may have (ClipPatch). */
export const CLIP_TEXT_LIMITS = { title: 70, hook_text: 60 } as const;
