import { useState, type DragEvent, type KeyboardEvent } from "react";
import type { TrackItem } from "@/api/types";
import { useDrag, useDragFrom } from "@/hooks/useDrag";
import { formatTimecode } from "@/lib/format";
import {
  itemLabel,
  LAYER_LABELS,
  type ItemDrag,
  type LayerName,
} from "@/lib/layers";
import {
  accepts,
  draggedKind,
  droppedMedia,
  type MediaDrag,
} from "@/lib/newLayerItems";
import { cn } from "@/lib/utils";

/** A press that moves less than this (px) is a click, not a drag. */
const DRAG_PX = 3;
const NUDGE_S = 0.1;
const NUDGE_FAST_S = 1;

/** A layer track row's height and gap (TrackLabels mirrors it). */
export const LAYER_ROW = "mt-0.5 h-5";

const TONES: Record<LayerName, string> = {
  broll: "border-primary/70 bg-primary/25",
  overlays: "border-highlight/70 bg-highlight/20",
  text: "border-foreground/50 bg-foreground/15",
  music: "border-success/70 bg-success/20",
  sfx: "border-warning/70 bg-warning/20",
  voiceover: "border-chart-2/70 bg-chart-2/20",
};

export interface TrackProps {
  name: LayerName;
  items: TrackItem[];
  /** Where an item lies on the row: left edge and width, in percent. */
  place: (item: TrackItem) => { left: number; width: number };
  /** The clip time (seconds after the cuts) under the pointer at clientX. */
  timeAt: (clientX: number) => number;
  /** A drag of item: the pointer is at clip time pointer, grab seconds
   * after where the item started when pressed; moves of one drag share
   * gesture. */
  onDrag: (
    item: TrackItem,
    drag: ItemDrag,
    pointer: number,
    grab: number,
    gesture: number,
  ) => void;
  /** Move item by seconds (arrow keys). */
  onNudge: (item: TrackItem, seconds: number) => void;
  /** The id of the selected item (Delete, cmd+C act on it). */
  selectedId: string | null;
  /** Pressing or focusing an item selects it. */
  onSelect: (item: TrackItem) => void;
  /** Pressing the row outside its items seeks there (clientX). */
  onSeek: (clientX: number) => void;
  /** A media library file of a kind the track holds dropped on the row at
   * clientX. */
  onDropMedia?: (clientX: number, media: MediaDrag) => void;
}

interface ItemBlockProps extends Omit<
  TrackProps,
  "items" | "place" | "onSeek" | "selectedId" | "onDropMedia"
> {
  selected: boolean;
  item: TrackItem;
  span: { left: number; width: number };
}

/** An item on a track: pressing or focusing it selects it, dragging its
 * body moves it, dragging its ends trims it; arrow keys move it 0.1 s
 * (shift: 1 s). */
function ItemBlock({
  name,
  item,
  span,
  selected,
  timeAt,
  onDrag,
  onNudge,
  onSelect,
}: ItemBlockProps) {
  const grab = (clientX: number) => timeAt(clientX) - item.start;
  const handler =
    (drag: ItemDrag) => (clientX: number, start: number, gesture: number) =>
      onDrag(item, drag, timeAt(clientX), start, gesture);
  const body = useDragFrom(grab, handler("move"), DRAG_PX);
  const head = useDragFrom(grab, handler("start"), DRAG_PX);
  const tail = useDragFrom(grab, handler("end"), DRAG_PX);
  const label = itemLabel(item);
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    const step = event.shiftKey ? NUDGE_FAST_S : NUDGE_S;
    onNudge(item, event.key === "ArrowLeft" ? -step : step);
  };
  const edge =
    "absolute inset-y-0 z-[1] w-1.5 cursor-ew-resize touch-none hover:bg-foreground/40";

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${LAYER_LABELS[name]}: ${label}, ${formatTimecode(item.start)} - ${formatTimecode(item.end)}`}
      title={label}
      aria-pressed={selected}
      data-testid="track-item"
      onKeyDown={onKeyDown}
      onFocus={() => onSelect(item)}
      {...body}
      className={cn(
        "absolute inset-y-0.5 box-border cursor-grab touch-none overflow-hidden rounded-sm border text-micro leading-[14px] whitespace-nowrap text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50 active:cursor-grabbing",
        TONES[name],
        selected && "ring-2 ring-foreground",
      )}
      style={{ left: `${span.left}%`, width: `max(4px, ${span.width}%)` }}
    >
      <span
        aria-hidden
        data-testid="item-start"
        {...head}
        className={cn(edge, "left-0")}
      />
      <span className="pointer-events-none block truncate px-2">{label}</span>
      <span
        aria-hidden
        data-testid="item-end"
        {...tail}
        className={cn(edge, "right-0")}
      />
    </div>
  );
}

/**
 * One layer track of the timeline: a row with a block per item (its label
 * is in TrackLabels' gutter),
 * placed by its clip time; blocks move and trim by dragging (see
 * ItemBlock), pressing the row elsewhere seeks. A media library file
 * dragged over a row that holds its kind lights the row up; dropping it
 * there adds it (onDropMedia).
 */
export function Track({
  items,
  place,
  onSeek,
  selectedId,
  onDropMedia,
  ...rest
}: TrackProps) {
  const seek = useDrag((clientX) => onSeek(clientX));
  const [over, setOver] = useState(false);
  const label = LAYER_LABELS[rest.name];
  const takes = (event: DragEvent) => {
    const kind = draggedKind(Array.from(event.dataTransfer.types));
    return (
      onDropMedia !== undefined && kind !== null && accepts(rest.name, kind)
    );
  };
  const onDragOver = (event: DragEvent) => {
    if (!takes(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setOver(true);
  };
  const onDrop = (event: DragEvent) => {
    setOver(false);
    if (!takes(event)) return;
    event.preventDefault();
    const media = droppedMedia(event.dataTransfer);
    if (media) onDropMedia?.(event.clientX, media);
  };
  return (
    <div
      role="group"
      aria-label={`${label} track`}
      {...seek}
      onDragOver={onDragOver}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      data-drop-target={over || undefined}
      className={cn(
        "relative cursor-pointer touch-none rounded-md bg-muted/25",
        LAYER_ROW,
        over && "bg-primary/20 ring-2 ring-primary",
      )}
    >
      {items.map((item) => (
        <ItemBlock
          key={item.id}
          item={item}
          span={place(item)}
          selected={item.id === selectedId}
          {...rest}
        />
      ))}
    </div>
  );
}
