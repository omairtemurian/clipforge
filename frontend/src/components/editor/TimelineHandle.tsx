import { DotsSixVerticalIcon } from "@phosphor-icons/react";
import type { KeyboardEvent } from "react";
import { useDrag } from "@/hooks/useDrag";
import { formatTimecode } from "@/lib/format";
import type { ClipRange, Handle } from "@/lib/timeline";
import { cn } from "@/lib/utils";

const NUDGE_S = 0.1;
const NUDGE_FAST_S = 1;

interface TimelineHandleProps {
  handle: Handle;
  clip: ClipRange;
  view: ClipRange;
  /** Move the handle to source time t; moves of one drag share gesture. */
  onMove: (handle: Handle, t: number, gesture?: number) => void;
  /** The source time under the pointer at clientX. */
  timeAt: (clientX: number) => number;
}

/** A draggable end of the clip box (trim/extend); arrow keys move it 0.1 s
 * (shift: 1 s), Home/End to the ends of the view. */
export function TimelineHandle({
  handle,
  clip,
  view,
  onMove,
  timeAt,
}: TimelineHandleProps) {
  const drag = useDrag((clientX, gesture) =>
    onMove(handle, timeAt(clientX), gesture),
  );
  const value = clip[handle];
  const onKeyDown = (event: KeyboardEvent) => {
    const step = event.shiftKey ? NUDGE_FAST_S : NUDGE_S;
    const moves: Record<string, number> = {
      ArrowLeft: value - step,
      ArrowRight: value + step,
      Home: view.start,
      End: view.end,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    onMove(handle, moves[event.key]);
  };

  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label={handle === "start" ? "Clip start" : "Clip end"}
      aria-valuemin={view.start}
      aria-valuemax={view.end}
      aria-valuenow={Number(value.toFixed(2))}
      aria-valuetext={formatTimecode(value)}
      onKeyDown={onKeyDown}
      {...drag}
      className={cn(
        "pointer-events-auto absolute inset-y-0 z-10 flex w-3 cursor-ew-resize touch-none items-center justify-center bg-primary text-primary-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        handle === "start" ? "left-0 rounded-l-md" : "right-0 rounded-r-md",
      )}
    >
      <DotsSixVerticalIcon className="size-3" aria-hidden />
    </div>
  );
}
