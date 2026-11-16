import { ClockIcon } from "@phosphor-icons/react";
import { progressText } from "@/lib/projectEta";
import type { ProjectProgress } from "@/lib/projectStatus";

/**
 * The pill centred on the dimmed thumbnail of a queued or running project:
 * a clock and "48% (ETA 5m)" in the ember accent. The ember fills the pill
 * from the left up to the overall percentage, so the pill is a progress bar.
 */
export function ProgressPill({
  name,
  progress,
}: {
  name: string;
  progress: ProjectProgress;
}) {
  const { label, percent, etaSeconds } = progress;
  const text = progressText(percent, etaSeconds);
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/45">
      <div
        role="progressbar"
        aria-label={`${name} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${label}, ${text}`}
        className="relative flex items-center gap-1.5 overflow-hidden rounded-full border border-primary bg-black/60 px-3.5 py-1.5 text-body font-medium text-white tabular-nums backdrop-blur-sm"
      >
        <span
          aria-hidden
          data-testid="progress-fill"
          className="absolute inset-y-0 left-0 bg-primary transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
        <ClockIcon className="relative size-4" aria-hidden />
        <span className="relative">{text}</span>
      </div>
    </div>
  );
}
