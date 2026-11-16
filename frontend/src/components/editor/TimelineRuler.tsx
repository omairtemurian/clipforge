import { useDrag } from "@/hooks/useDrag";
import { formatDuration } from "@/lib/format";
import { spanPercent, tickStep, ticks, type ClipRange } from "@/lib/timeline";
import { cn } from "@/lib/utils";

interface TimelineRulerProps {
  view: ClipRange;
  /** The drawn width of the view in px (zoomed). */
  width: number;
  timeAt: (clientX: number) => number;
  onSeek: (t: number) => void;
}

/** How a label at t lines up with its tick: centered, but kept inside the
 * ruler near its ends. */
function edgeAlign(t: number, view: ClipRange, step: number): string {
  if (t - view.start < step / 4) return "";
  if (view.end - t < step / 4) return "-translate-x-full";
  return "-translate-x-1/2";
}

/** The time ruler: a label at every round step of the view and a dot
 * between labels; pressing or dragging on it moves the playhead. */
export function TimelineRuler({
  view,
  width,
  timeAt,
  onSeek,
}: TimelineRulerProps) {
  const step = tickStep(view.end - view.start, width);
  const scrub = useDrag((clientX) => onSeek(timeAt(clientX)));
  const at = (t: number) => `${spanPercent(view.start, t, view).width}%`;

  return (
    <div
      aria-label="Time ruler"
      {...scrub}
      className="relative h-6 cursor-pointer touch-none text-micro text-muted-foreground"
    >
      {ticks(view.start, view.end, step).map((t) => (
        <span
          key={t}
          aria-hidden
          className={cn(
            "absolute top-1 tabular-nums",
            edgeAlign(t, view, step),
          )}
          style={{ left: at(t) }}
        >
          {formatDuration(t)}
        </span>
      ))}
      {ticks(view.start + step / 2, view.end, step).map((t) => (
        <span
          key={`dot-${t}`}
          aria-hidden
          className="absolute top-2.5 size-0.5 -translate-x-1/2 rounded-full bg-muted-foreground/60"
          style={{ left: at(t) }}
        />
      ))}
    </div>
  );
}
