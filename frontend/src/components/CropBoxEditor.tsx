import {
  useRef,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import { nextGesture } from "@/hooks/useGesture";
import {
  moveRect,
  resizeFree,
  resizeRect,
  type Corner,
  type Rect,
} from "@/lib/cropFrame";
import { cn } from "@/lib/utils";

const CORNERS: { corner: Corner; label: string; className: string }[] = [
  {
    corner: "nw",
    label: "top left",
    className: "-top-1.5 -left-1.5 cursor-nwse-resize",
  },
  {
    corner: "ne",
    label: "top right",
    className: "-top-1.5 -right-1.5 cursor-nesw-resize",
  },
  {
    corner: "sw",
    label: "bottom left",
    className: "-bottom-1.5 -left-1.5 cursor-nesw-resize",
  },
  {
    corner: "se",
    label: "bottom right",
    className: "-right-1.5 -bottom-1.5 cursor-nwse-resize",
  },
];

/** An arrow key's move of the box, in fractions of the frame's width
 * (with shift: ARROW_FAST). */
const ARROW = 0.01;
const ARROW_FAST = 0.05;
const ARROWS: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
};

/** How a corner drag resizes the box: keeping its shape, with its width
 * between minWidth and maxWidth; or in any shape, each side at least
 * minSize. */
export type BoxResize =
  | { shape: "keep"; minWidth: number; maxWidth: number }
  | { shape: "free"; minSize: number };

interface Drag {
  corner: Corner | null;
  x: number;
  y: number;
  rect: Rect;
  gesture: number;
}

interface CropBoxEditorProps {
  /** The source frame's size in pixels. */
  frame: { width: number; height: number };
  /** The box, in source pixels. */
  rect: Rect;
  resize: BoxResize;
  /** The box's accessible name. */
  label: string;
  /** Called with the moved or resized box; changes of one drag share a
   * gesture (they undo at once). */
  onChange: (rect: Rect, gesture: number) => void;
  /** Dims the frame outside the box. */
  dimOutside?: boolean;
  /** Shown inside the box (a tag naming it). */
  children?: ReactNode;
}

const percent = (value: number, total: number) => `${(value / total) * 100}%`;

/**
 * A box over the source frame (inside SourceFrame, which it measures as
 * its parent) that dragging moves and dragging a corner resizes, kept
 * inside the frame; the arrow keys move it while it is focused (shift:
 * faster).
 */
export function CropBoxEditor({
  frame,
  rect,
  resize,
  label,
  onChange,
  dimOutside = true,
  children,
}: CropBoxEditorProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);

  const start = (event: PointerEvent, corner: Corner | null) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    event.preventDefault();
    drag.current = {
      corner,
      x: event.clientX,
      y: event.clientY,
      rect,
      gesture: nextGesture(),
    };
    boxRef.current?.setPointerCapture?.(event.pointerId);
  };

  const move = (event: PointerEvent) => {
    const active = drag.current;
    const bounds = boxRef.current?.parentElement?.getBoundingClientRect();
    if (!active || !bounds?.width) return;
    const scale = frame.width / bounds.width;
    const dx = (event.clientX - active.x) * scale;
    const dy = (event.clientY - active.y) * scale;
    let next: Rect;
    if (!active.corner) next = moveRect(active.rect, dx, dy, frame);
    else if (resize.shape === "keep") {
      next = resizeRect(active.rect, active.corner, dx, dy, frame, resize);
    } else {
      next = resizeFree(
        active.rect,
        active.corner,
        dx,
        dy,
        frame,
        resize.minSize,
      );
    }
    onChange(next, active.gesture);
  };

  const end = () => {
    drag.current = null;
  };

  const nudge = (event: KeyboardEvent) => {
    const arrow = ARROWS[event.key];
    if (!arrow) return;
    event.preventDefault();
    const step = (event.shiftKey ? ARROW_FAST : ARROW) * frame.width;
    onChange(
      moveRect(rect, arrow[0] * step, arrow[1] * step, frame),
      nextGesture(),
    );
  };

  return (
    <div
      ref={boxRef}
      role="group"
      aria-label={label}
      aria-description="Drag to move, drag a corner to resize, or use the arrow keys."
      tabIndex={0}
      onPointerDown={(event) => start(event, null)}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      onKeyDown={nudge}
      className={cn(
        "absolute cursor-move border-2 border-primary outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        dimOutside && "shadow-[0_0_0_9999px_rgb(0_0_0/0.6)]",
      )}
      style={{
        left: percent(rect.x, frame.width),
        top: percent(rect.y, frame.height),
        width: percent(rect.width, frame.width),
        height: percent(rect.height, frame.height),
      }}
    >
      {children}
      {CORNERS.map(({ corner, label: name, className }) => (
        <button
          key={corner}
          type="button"
          tabIndex={-1}
          aria-label={`Resize from the ${name} corner`}
          onPointerDown={(event) => start(event, corner)}
          className={`absolute size-3 rounded-sm border-2 border-primary bg-background ${className}`}
        />
      ))}
    </div>
  );
}
