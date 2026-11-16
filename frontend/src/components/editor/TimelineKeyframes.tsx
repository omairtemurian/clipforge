import { useRef, type KeyboardEvent } from "react";
import type { CropPoint } from "@/api/types";
import { useDrag } from "@/hooks/useDrag";
import { formatTimecode } from "@/lib/format";
import { spanPercent, type ClipRange } from "@/lib/timeline";
import { cn } from "@/lib/utils";

export interface KeyframeRowProps {
  /** The fixed scene's span and its keyframes. */
  scene: ClipRange;
  keys: CropPoint[];
  /** The keyframe at the playhead, if any. */
  current?: number;
  onSeek: (t: number) => void;
  /** Move the keyframe at from to source time to; moves of one drag share
   * gesture. */
  onMove: (from: number, to: number, gesture: number) => void;
  onDelete: (t: number) => void;
}

interface DiamondProps {
  t: number;
  active: boolean;
  view: ClipRange;
  timeAt: (clientX: number) => number;
  row: KeyframeRowProps;
}

/** How far (px) the pointer moves before pressing a diamond drags it. */
const DRAG_PX = 3;

/** A keyframe's diamond: clicking it seeks there, dragging moves it, and
 * Delete or Backspace removes it. */
function Diamond({ t, active, view, timeAt, row }: DiamondProps) {
  const press = useRef({ gesture: 0, x: 0, key: 0, moved: false });
  const drag = useDrag((clientX, gesture) => {
    const state = press.current;
    if (state.gesture !== gesture) {
      press.current = { gesture, x: clientX, key: t, moved: false };
      return;
    }
    if (!state.moved && Math.abs(clientX - state.x) < DRAG_PX) return;
    state.moved = true;
    const to = state.key + timeAt(clientX) - timeAt(state.x);
    if (to !== t) row.onMove(t, to, gesture);
  });
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Delete" && event.key !== "Backspace") return;
    event.preventDefault();
    event.stopPropagation();
    row.onDelete(t);
  };
  const left = spanPercent(view.start, t, view).width;
  return (
    <button
      type="button"
      aria-label={`Keyframe ${formatTimecode(t)}`}
      aria-pressed={active}
      onClick={() => row.onSeek(t)}
      onKeyDown={onKeyDown}
      {...drag}
      className={cn(
        "absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 cursor-ew-resize touch-none rounded-[2px] border outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        active
          ? "border-primary bg-primary"
          : "border-primary bg-background hover:bg-primary/40",
      )}
      style={{ left: `${left}%` }}
    />
  );
}

/**
 * The keyframes row of the fixed scene at the playhead: its span shaded,
 * with a diamond per keyframe of its crop window (see Diamond).
 */
export function TimelineKeyframes({
  view,
  timeAt,
  ...row
}: KeyframeRowProps & {
  view: ClipRange;
  timeAt: (clientX: number) => number;
}) {
  const span = spanPercent(row.scene.start, row.scene.end, view);
  return (
    <div aria-label="Keyframes" className="relative mt-1 h-3.5">
      <div
        aria-hidden
        className="absolute inset-y-0 rounded-sm bg-primary/10"
        style={{ left: `${span.left}%`, width: `${span.width}%` }}
      />
      {row.keys.map((key, index) => (
        <Diamond
          key={index}
          t={key.t}
          active={key.t === row.current}
          view={view}
          timeAt={timeAt}
          row={row}
        />
      ))}
    </div>
  );
}
