import { useRef, useState } from "react";
import type { EdlItem, ProEditTiming } from "@/api/types";
import { useDrag } from "@/hooks/useDrag";
import { useElementWidth } from "@/hooks/useElementWidth";
import { formatTimecode } from "@/lib/format";
import type { ItemDrag } from "@/lib/layers";
import { clamp, tickStep, ticks } from "@/lib/timeline";
import { cn } from "@/lib/utils";
import { EdlItemBlock, ROW_PX } from "./EdlItemBlock";
import {
  dragEdlItem,
  guideLabel,
  KIND_LABELS,
  LANES,
  laneItems,
  laneRows,
  nudgeEdlItem,
  snapTargets,
  spanChanged,
  withSpan,
  type EdlDrag,
} from "./laneMath";

/** How near (px) a dragged edge must come to a target to snap to it. */
const SNAP_PX = 8;
const RULER = "h-6";

const TONES: Record<string, string> = {
  zoom: "border-primary/70 bg-primary/25",
  fx: "border-highlight/70 bg-highlight/20",
  grade: "border-chart-2/70 bg-chart-2/20",
  overlay: "border-foreground/50 bg-foreground/15",
  captions: "border-chart-4/70 bg-chart-4/20",
  sfx: "border-warning/70 bg-warning/20",
  music: "border-success/70 bg-success/20",
  audio_fx: "border-chart-5/70 bg-chart-5/20",
};

export interface EdlLanesProps {
  items: EdlItem[];
  timing: ProEditTiming;
  /** Where the preview is (clip seconds). */
  playhead: number;
  /** The selected item (shown in the readout and the inspector). */
  selectedId: number | null;
  onSelect: (id: number) => void;
  /** No edits (a job of the variant is queued or running). */
  disabled: boolean;
  /** The items after an edit of one of them (a drag or a nudge). */
  onCommit: (items: EdlItem[]) => void;
  /** Pressing a lane outside its items seeks the previews there. */
  onSeek: (t: number) => void;
}

/** The selected item's kind, times and reason, or the snapping preview's
 * guide while an item is dragged. */
function Readout({ item, drag }: { item?: EdlItem; drag: EdlDrag | null }) {
  if (drag?.guide) {
    return (
      <p role="status" className="text-body text-muted-foreground">
        Snaps to {guideLabel(drag.guide)} at {formatTimecode(drag.guide.t)}
      </p>
    );
  }
  if (!item) {
    return (
      <p className="text-body text-muted-foreground">
        Select an item to see why it is there.
      </p>
    );
  }
  const span = drag ?? { start: item.t_start, end: item.t_end };
  return (
    <p aria-label="Selected item" className="text-body">
      <span className="font-medium">{KIND_LABELS[item.kind]}</span>{" "}
      <span className="text-muted-foreground tabular-nums">
        {formatTimecode(span.start)} – {formatTimecode(span.end)} ·{" "}
        {item.source === "manual" ? "edited" : "auto"}
      </span>
      <span className="block text-muted-foreground">Why: {item.reason}</span>
    </p>
  );
}

/**
 * The EDL lanes of a Pro Edit plan (SPEC-v3 3.8): a ruler with the clip's
 * beats, a lane per track with its items (overlapping ones on rows of
 * their own), the playhead, and while an item is dragged the guide of
 * what it snaps to (word starts, beats, other items' edges, the playhead;
 * then the frame grid). A finished drag or an arrow-key nudge commits the
 * edited items; the selected item's reason shows below.
 */
export function EdlLanes({
  items,
  timing,
  playhead,
  selectedId,
  onSelect,
  disabled,
  onCommit,
  onSeek,
}: EdlLanesProps) {
  const area = useRef<HTMLDivElement>(null);
  const width = useElementWidth(area);
  const [drag, setDrag] = useState<(EdlDrag & { id: number }) | null>(null);
  const duration = Math.max(timing.duration, 1 / timing.fps);

  const timeAt = (clientX: number) => {
    const box = area.current?.getBoundingClientRect();
    if (!box || box.width <= 0) return 0;
    return clamp(((clientX - box.left) / box.width) * duration, 0, duration);
  };
  const seek = useDrag((clientX) => onSeek(timeAt(clientX)));
  const onDrag = (
    item: EdlItem,
    kind: ItemDrag,
    pointer: number,
    grab: number,
  ) => {
    const px = area.current?.getBoundingClientRect().width ?? 0;
    const tolerance = px > 0 ? (SNAP_PX / px) * duration : 0;
    const targets = snapTargets(timing, items, item.id, playhead);
    const next = dragEdlItem(
      item,
      { drag: kind, pointer, grab, targets, tolerance },
      timing,
    );
    setDrag({ ...next, id: item.id });
  };
  const onDragEnd = (item: EdlItem, commit: boolean) => {
    const span = drag?.id === item.id ? drag : null;
    setDrag(null);
    if (commit && span && spanChanged(item, span)) {
      onCommit(withSpan(items, item.id, span));
    }
  };
  const onNudge = (item: EdlItem, frames: number) => {
    const span = nudgeEdlItem(item, frames / timing.fps, timing);
    if (spanChanged(item, span)) onCommit(withSpan(items, item.id, span));
  };
  const selected = items.find((item) => item.id === selectedId);
  const step = tickStep(duration, width, 56);
  const percent = (t: number) => `${(t / duration) * 100}%`;
  const lanes = LANES.map((lane) => {
    const own = laneItems(items, lane);
    const rows = laneRows(own);
    const count = Math.max(1, ...[...rows.values()].map((row) => row + 1));
    return { lane, own, rows, height: count * ROW_PX };
  });

  return (
    <section aria-label="EDL lanes" className="flex flex-col gap-3">
      <div className="flex gap-2">
        <div className="flex w-20 shrink-0 flex-col gap-1 text-micro text-muted-foreground">
          <div className={RULER} />
          {lanes.map(({ lane, height }) => (
            <div key={lane.id} className="flex items-center" style={{ height }}>
              {lane.label}
            </div>
          ))}
        </div>
        <div ref={area} className="relative min-w-0 flex-1" {...seek}>
          <div
            aria-hidden
            className={cn("relative border-b border-border", RULER)}
          >
            {ticks(0, duration, step).map((t) => (
              <span
                key={t}
                className={cn(
                  "absolute top-0 text-micro text-muted-foreground tabular-nums",
                  t > 0 && "-translate-x-1/2",
                )}
                style={{ left: percent(t) }}
              >
                {formatTimecode(t).slice(3, 8)}
              </span>
            ))}
            {timing.beats.map((t) => (
              <span
                key={t}
                data-testid="beat-mark"
                className="absolute bottom-0 h-1.5 w-px bg-success"
                style={{ left: percent(t) }}
              />
            ))}
          </div>
          <div className="flex flex-col gap-1 pt-1">
            {lanes.map(({ lane, own, rows, height }) => (
              <div
                key={lane.id}
                role="group"
                aria-label={`${lane.label} lane`}
                className="relative cursor-pointer rounded-md bg-muted/25"
                style={{ height }}
              >
                {own.map((item) => (
                  <EdlItemBlock
                    key={item.id}
                    item={item}
                    span={
                      drag?.id === item.id
                        ? drag
                        : { start: item.t_start, end: item.t_end }
                    }
                    duration={duration}
                    row={rows.get(item.id) ?? 0}
                    tone={TONES[lane.id]}
                    selected={item.id === selectedId}
                    disabled={disabled}
                    timeAt={timeAt}
                    onDrag={onDrag}
                    onDragEnd={onDragEnd}
                    onNudge={onNudge}
                    onSelect={(chosen) => onSelect(chosen.id)}
                  />
                ))}
              </div>
            ))}
          </div>
          <span
            aria-hidden
            data-testid="playhead"
            className="pointer-events-none absolute inset-y-0 w-0.5 bg-foreground"
            style={{ left: percent(clamp(playhead, 0, duration)) }}
          />
          {drag?.guide && (
            <span
              aria-hidden
              data-testid="snap-guide"
              className="pointer-events-none absolute inset-y-0 w-px border-l border-dashed border-primary"
              style={{ left: percent(drag.guide.t) }}
            />
          )}
        </div>
      </div>
      <Readout item={selected} drag={drag} />
    </section>
  );
}
