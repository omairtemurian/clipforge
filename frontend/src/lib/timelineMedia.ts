/**
 * Pictures and sound on the timeline: which filmstrip tile each slot of
 * the video row shows, and the waveform's level per column of the audio
 * row.
 */
import type { Waveform } from "@/api/types";
import { clamp, type ClipRange } from "@/lib/timeline";

/** A filmstrip image (GET /clips/{id}/filmstrip): count tiles of width /
 * height tileAspect in a row; tile i shows source time start + i * interval. */
export interface FilmstripStrip {
  start: number;
  interval: number;
  count: number;
  tileAspect: number;
}

/** A slot of the video row: x px from its left edge, showing tile index. */
export interface FilmstripSlot {
  left: number;
  index: number;
}

/**
 * The slots of a video row width px wide and height px tall that shows
 * view: tiles keep their aspect, side by side, each showing the strip's
 * tile of the source time at its middle.
 */
export function filmstripSlots(
  strip: FilmstripStrip,
  view: ClipRange,
  width: number,
  height: number,
): FilmstripSlot[] {
  const tile = height * strip.tileAspect;
  const span = view.end - view.start;
  if (tile <= 0 || width <= 0 || span <= 0 || strip.count < 1) return [];
  const slots: FilmstripSlot[] = [];
  for (let left = 0; left < width; left += tile) {
    const t = view.start + ((left + tile / 2) / width) * span;
    const index = Math.floor((t - strip.start) / strip.interval);
    slots.push({ left, index: clamp(index, 0, strip.count - 1) });
  }
  return slots;
}

/**
 * The level (0-1, the loudest peak of the wave = 1) of each of columns
 * equal columns across view: the loudest peak in its time span, 0 where
 * the wave has no peaks.
 */
export function waveformColumns(
  wave: Waveform,
  view: ClipRange,
  columns: number,
): number[] {
  const loudest = wave.peaks.reduce((top, peak) => Math.max(top, peak), 0);
  const span = view.end - view.start;
  if (columns <= 0 || span <= 0) return [];
  const rate = wave.peaks_per_second;
  const levels: number[] = [];
  for (let column = 0; column < columns; column += 1) {
    const from = view.start + (column / columns) * span;
    const to = view.start + ((column + 1) / columns) * span;
    const first = Math.max(0, Math.floor((from - wave.start) * rate));
    const last = Math.min(
      wave.peaks.length,
      Math.max(first + 1, Math.ceil((to - wave.start) * rate)),
    );
    let peak = 0;
    for (let index = first; index < last; index += 1) {
      peak = Math.max(peak, wave.peaks[index]);
    }
    levels.push(loudest > 0 ? peak / loudest : 0);
  }
  return levels;
}
