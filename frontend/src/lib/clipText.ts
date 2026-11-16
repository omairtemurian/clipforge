/**
 * The texts of a clip that the Text panel edits (title, hook, description,
 * hashtags) with the limits of the API (models.ClipPatch, ClipText).
 */

export const TITLE_MAX = 70;
export const HOOK_MAX = 60;
export const DESCRIPTION_MAX = 300;
export const HASHTAGS_MIN = 3;
export const HASHTAGS_MAX = 8;

/** The hashtags typed in text: separated by spaces, commas or "#", with
 * no "#" kept and no repeats (ignoring case). */
export function parseHashtags(text: string): string[] {
  const seen = new Set<string>();
  return text
    .split(/[\s,#]+/)
    .filter((tag) => tag !== "")
    .filter((tag) => {
      const key = tag.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

/** The hashtags of `value` followed by those typed in `text` that are not
 * among them (ignoring case), at most `max` in all. */
export function addHashtags(
  value: string[],
  text: string,
  max: number,
): string[] {
  const seen = new Set(value.map((tag) => tag.toLowerCase()));
  const added = parseHashtags(text).filter((tag) => {
    const key = tag.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return [...value, ...added].slice(0, max);
}

/** The hashtags as shown in the input: "#pizza #funny". */
export function formatHashtags(tags: string[]): string {
  return tags.map((tag) => `#${tag}`).join(" ");
}

export interface TextFields {
  title: string;
  hook_text: string;
  description: string;
  hashtags: string[];
}

/** What is wrong with texts, by field (a field that is fine is absent). */
export type TextProblems = Partial<Record<keyof TextFields, string>>;

/** The problems of texts that the API would refuse. */
export function textProblems(texts: TextFields): TextProblems {
  const problems: TextProblems = {};
  if (texts.title.length > TITLE_MAX) {
    problems.title = `At most ${TITLE_MAX} characters.`;
  }
  if (texts.hook_text.length > HOOK_MAX) {
    problems.hook_text = `At most ${HOOK_MAX} characters.`;
  }
  if (texts.description.length > DESCRIPTION_MAX) {
    problems.description = `At most ${DESCRIPTION_MAX} characters.`;
  }
  const count = texts.hashtags.length;
  if (count < HASHTAGS_MIN || count > HASHTAGS_MAX) {
    problems.hashtags = `Use ${HASHTAGS_MIN} to ${HASHTAGS_MAX} hashtags (now ${count}).`;
  }
  return problems;
}
