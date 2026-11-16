/**
 * The texts of a clip's caption words: caption_overrides hold the words
 * whose text the editor changed, matched to the transcript's words by their
 * times (the backend matches them to the millisecond).
 */
import type { Word } from "@/api/types";
import type { ClipRange, CutRange } from "@/lib/timeline";

function sameTimes(a: Word, b: Word): boolean {
  return (
    Math.round(a.start * 1000) === Math.round(b.start * 1000) &&
    Math.round(a.end * 1000) === Math.round(b.end * 1000)
  );
}

/** The words that start in the clip and outside its cuts, in order. */
export function captionedWords(
  words: Word[],
  range: ClipRange,
  cuts: CutRange[],
): Word[] {
  return words.filter(
    (word) =>
      word.start >= range.start &&
      word.start < range.end &&
      !cuts.some(([from, to]) => word.start >= from && word.start < to),
  );
}

/** The text captions show for word: its override's, else its own. */
export function captionText(word: Word, overrides: Word[]): string {
  const override = overrides.find((item) => sameTimes(item, word));
  return override ? override.text : word.text.trim();
}

/**
 * overrides with the text of word set to text; a text equal to the word's
 * own removes its override. A blank text is kept: it hides the word. The
 * text is kept as typed (the backend strips it).
 */
export function withWordText(
  overrides: Word[],
  word: Word,
  text: string,
): Word[] {
  const others = overrides.filter((item) => !sameTimes(item, word));
  return text === word.text.trim() ? others : [...others, { ...word, text }];
}
