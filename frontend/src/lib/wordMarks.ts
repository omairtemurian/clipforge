/**
 * The marks of a clip's caption words (caption_style.word_marks): per word
 * emphasis, emoji, censor and color, from the AI or the editor. A mark is
 * matched to its word by the word's start, to the millisecond (as the
 * backend does), and an editor ("user") mark beats an AI mark of the word.
 */
import type { CaptionMark, Word } from "@/api/types";

/** What the editor sets of a word; null lets the clip decide. */
export type MarkFields = Pick<
  CaptionMark,
  "emphasis" | "emoji" | "censor" | "color"
>;

const NO_MARK: MarkFields = {
  emphasis: null,
  emoji: null,
  censor: null,
  color: null,
};

/** A few emojis offered for a word, besides typing one. */
export const EMOJI_CHOICES = ["🔥", "😂", "💯", "🚀", "💡", "❤️", "👀", "⭐"];

function ms(seconds: number): number {
  return Math.round(seconds * 1000);
}

/** Whether text is an emoji the backend takes: one non-ASCII character,
 * maybe followed by VARIATION SELECTOR-16. */
export function isEmoji(text: string): boolean {
  const [first, ...rest] = [...text];
  const nonAscii = (first?.codePointAt(0) ?? 0) > 0x7f;
  return nonAscii && (rest.length === 0 || rest.join("") === "\ufe0f");
}

/** The mark that applies to word: the editor's, else the AI's. */
export function markOf(
  marks: CaptionMark[] | null,
  word: Word,
): CaptionMark | undefined {
  const own = (marks ?? []).filter((mark) => ms(mark.start) === ms(word.start));
  return own.filter((mark) => mark.source === "user").at(-1) ?? own.at(-1);
}

/** The fields of word's mark (all null without one). */
export function markFields(
  marks: CaptionMark[] | null,
  word: Word,
): MarkFields {
  const mark = markOf(marks, word);
  if (!mark) return NO_MARK;
  const { emphasis, emoji, censor, color } = mark;
  return { emphasis, emoji, censor, color };
}

/** Whether a mark of word sets anything. */
export function isMarked(marks: CaptionMark[] | null, word: Word): boolean {
  return Object.values(markFields(marks, word)).some((value) => value !== null);
}

/**
 * marks with the editor's mark of word changed by change, starting from the
 * mark that applies now. A mark that sets nothing is dropped unless an AI
 * mark of the word is left, which it must still beat.
 */
export function withMark(
  marks: CaptionMark[] | null,
  word: Word,
  change: Partial<MarkFields>,
): CaptionMark[] {
  const fields = { ...markFields(marks, word), ...change };
  const others = (marks ?? []).filter(
    (mark) => mark.source !== "user" || ms(mark.start) !== ms(word.start),
  );
  const empty = Object.values(fields).every((value) => value === null);
  const hasAi = others.some((mark) => ms(mark.start) === ms(word.start));
  if (empty && !hasAi) return others;
  return [...others, { start: word.start, ...fields, source: "user" }];
}

/** marks without the editor's mark of word: the AI's applies again. */
export function withoutUserMark(
  marks: CaptionMark[] | null,
  word: Word,
): CaptionMark[] {
  return (marks ?? []).filter(
    (mark) => mark.source !== "user" || ms(mark.start) !== ms(word.start),
  );
}

/** The diarized speakers of words, in order of first word; the unknown
 * speaker ("") is left out. */
export function speakersOf(words: Word[]): string[] {
  return [...new Set(words.map((word) => word.speaker))].filter(Boolean);
}
