/** The longest side a ratio may have per unit of its shortest (the
 * backend's aspect.MAX_RATIO). */
export const MAX_RATIO = 4;

/**
 * The "W:H" aspect that text names ("3:4", "3 : 4", "3x4"), or null if it
 * is not one the backend accepts: two whole numbers of 1 to 3 digits, not
 * zero, with the long side at most MAX_RATIO times the short one.
 */
export function parseRatio(text: string): string | null {
  const match = /^\s*(\d{1,3})\s*[:x/]\s*(\d{1,3})\s*$/i.exec(text);
  if (!match) return null;
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (width < 1 || height < 1) return null;
  if (Math.max(width, height) > MAX_RATIO * Math.min(width, height))
    return null;
  return `${width}:${height}`;
}
