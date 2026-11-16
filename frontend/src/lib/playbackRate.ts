/** The preview's playback speeds, slowest first (the editor's < and >). */
export const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2] as const;

/** The speed steps steps faster (positive) or slower than rate, within
 * PLAYBACK_RATES; a rate between two steps counts as the slower one. */
export function stepRate(rate: number, steps: number): number {
  let index = 0;
  PLAYBACK_RATES.forEach((each, i) => {
    if (each <= rate) index = i;
  });
  const next = Math.min(PLAYBACK_RATES.length - 1, Math.max(0, index + steps));
  return PLAYBACK_RATES[next];
}

/** "0.5×", "1×", "1.25×". */
export function rateLabel(rate: number): string {
  return `${rate}×`;
}
