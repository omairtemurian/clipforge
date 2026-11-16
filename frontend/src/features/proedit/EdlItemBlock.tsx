import type { KeyboardEvent } from "react";
import type { EdlItem } from "@/api/types";
import { useDragFrom } from "@/hooks/useDrag";
import { formatTimecode } from "@/lib/format";
import type { ItemDrag } from "@/lib/layers";
import type { Span } from "@/lib/snap";
import { cn } from "@/lib/utils";
import { KIND_LABELS } from "./laneMath";

/** A press that moves less than this (px) is a click, not a drag. */
const DRAG_PX = 3;
/** The height of one row of a lane, px. */
export const ROW_PX = 24;

export interface EdlItemBlockProps {
  item: EdlItem;
  /** Where the item lies now (its drag's span while it is dragged). */
  span: Span;
  duration: number;
  row: number;
  tone: string;
  selected: boolean;
  disabled: boolean;
  /** The clip time under the pointer at clientX. */
  timeAt: (clientX: number) => number;
  /** A drag of item: the pointer is at clip time pointer, grab seconds
   * after where the item started when pressed. */
  onDrag: (
    item: EdlItem,
    drag: ItemDrag,
    pointer: number,
    grab: number,
  ) => void;
  /** The drag of item ended: commit it, or drop it (cancelled). */
  onDragEnd: (item: EdlItem, commit: boolean) => void;
  /** Move item by frames (arrow keys). */
  onNudge: (item: EdlItem, frames: number) => void;
  onSelect: (item: EdlItem) => void;
}

/**
 * One edit decision on its lane: its kind, and its times and reason in
 * its tooltip and accessible name. Dragging its body moves it,
 * dragging its ends trims it; arrow keys move it a frame (shift: ten).
 */
export function EdlItemBlock({
  item,
  span,
  duration,
  row,
  tone,
  selected,
  disabled,
  timeAt,
  onDrag,
  onDragEnd,
  onNudge,
  onSelect,
}: EdlItemBlockProps) {
  const grab = (clientX: number) => {
    onSelect(item);
    return timeAt(clientX) - item.t_start;
  };
  const move = (drag: ItemDrag) => (clientX: number, start: number) =>
    onDrag(item, drag, timeAt(clientX), start);
  const end = (moved: boolean, cancelled: boolean) => {
    if (moved) onDragEnd(item, !cancelled);
  };
  const body = useDragFrom(grab, move("move"), DRAG_PX, end);
  const head = useDragFrom(grab, move("start"), DRAG_PX, end);
  const tail = useDragFrom(grab, move("end"), DRAG_PX, end);
  const label = KIND_LABELS[item.kind];
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    if (disabled) return;
    const step = event.shiftKey ? 10 : 1;
    onNudge(item, event.key === "ArrowLeft" ? -step : step);
  };
  const left = (span.start / duration) * 100;
  const width = ((span.end - span.start) / duration) * 100;
  const edge =
    "absolute inset-y-0 z-[1] w-1.5 cursor-ew-resize touch-none hover:bg-foreground/40";
  const drag = disabled ? {} : body;

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${label}, ${formatTimecode(span.start)} - ${formatTimecode(span.end)}. Why: ${item.reason}`}
      aria-pressed={selected}
      aria-disabled={disabled || undefined}
      title={`${label}: ${item.reason}`}
      data-testid="edl-item"
      data-source={item.source}
      onKeyDown={onKeyDown}
      onFocus={() => onSelect(item)}
      {...drag}
      className={cn(
        "absolute box-border touch-none overflow-hidden rounded-sm border text-micro leading-[18px] whitespace-nowrap text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        disabled
          ? "cursor-default opacity-70"
          : "cursor-grab active:cursor-grabbing",
        tone,
        item.source === "manual" && "border-dashed",
        selected && "z-[2] ring-2 ring-foreground",
      )}
      style={{
        left: `${left}%`,
        width: `max(6px, ${width}%)`,
        top: row * ROW_PX + 2,
        height: ROW_PX - 4,
      }}
    >
      {!disabled && (
        <span
          aria-hidden
          data-testid="edl-item-start"
          {...head}
          className={cn(edge, "left-0")}
        />
      )}
      <span className="pointer-events-none block truncate px-2">{label}</span>
      {!disabled && (
        <span
          aria-hidden
          data-testid="edl-item-end"
          {...tail}
          className={cn(edge, "right-0")}
        />
      )}
    </div>
  );
}
