/**
 * The text forms of the caption word lists: the censor list and the brand
 * vocabulary's terms (one entry per line) and its corrections (one
 * "heard = correct" per line).
 */

/** The entries of text: one per line, trimmed, blank lines left out. */
export function linesOf(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** corrections as lines of "heard = correct". */
export function correctionsText(corrections: Record<string, string>): string {
  return Object.entries(corrections)
    .map(([heard, correct]) => `${heard} = ${correct}`)
    .join("\n");
}

export interface ParsedCorrections {
  corrections: Record<string, string>;
  /** The 1-based numbers of the lines that are not "heard = correct". */
  bad: number[];
}

/** The corrections of text, one "heard = correct" per line (blank lines
 * skipped); a line without both sides is bad. */
export function parseCorrections(text: string): ParsedCorrections {
  const corrections: Record<string, string> = {};
  const bad: number[] = [];
  text.split("\n").forEach((line, index) => {
    if (!line.trim()) return;
    const at = line.indexOf("=");
    const heard = line.slice(0, at).trim();
    const correct = line.slice(at + 1).trim();
    if (at < 0 || !heard || !correct) bad.push(index + 1);
    else corrections[heard] = correct;
  });
  return { corrections, bad };
}
