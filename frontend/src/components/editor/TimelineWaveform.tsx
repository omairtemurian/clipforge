import type { Waveform } from "@/api/types";
import type { ClipRange } from "@/lib/timeline";
import { waveformColumns } from "@/lib/timelineMedia";

/** Px per waveform bar (bar plus gap). */
const BAR_PX = 3;

interface TimelineWaveformProps {
  wave: Waveform;
  view: ClipRange;
  /** The drawn width of the row in px. */
  width: number;
}

/** The audio row: a bar per few px, as tall as the loudest sound under it
 * (the loudest of the wave fills the row), mirrored around the middle. */
export function TimelineWaveform({ wave, view, width }: TimelineWaveformProps) {
  const columns = Math.max(1, Math.floor(width / BAR_PX));
  const levels = waveformColumns(wave, view, columns);
  const path = levels
    .map((level, column) => {
      const half = Math.max(0.02, level) * 48;
      return `M${column} ${50 - half}h0.6v${2 * half}h-0.6z`;
    })
    .join("");
  return (
    <svg
      aria-hidden
      data-testid="waveform"
      viewBox={`0 0 ${columns} 100`}
      preserveAspectRatio="none"
      className="absolute inset-0 size-full text-muted-foreground"
    >
      <path d={path} fill="currentColor" />
    </svg>
  );
}
