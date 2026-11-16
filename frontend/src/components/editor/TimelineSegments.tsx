import { formatTimecode } from "@/lib/format";
import { spanPercent, type ClipRange, type CutRange } from "@/lib/timeline";
import { cn } from "@/lib/utils";

interface TimelineSegmentsProps {
  view: ClipRange;
  /** The kept parts of the clip (segments). */
  parts: CutRange[];
  selected: CutRange | null;
  /** The label of a segment: how its scene is framed. */
  labelAt: (part: CutRange) => string;
  /** The row's width in pixels (0 until measured). */
  width?: number;
  onSelect: (part: CutRange) => void;
}

const CHAR_PX = 6;
const PADDING_PX = 14;

/** Whether the label fits in the chip's pixels; unmeasured rows show it. */
function labelFits(label: string, chipPx: number): boolean {
  return chipPx <= 0 || chipPx >= label.length * CHAR_PX + PADDING_PX;
}

function same(a: CutRange | null, b: CutRange): boolean {
  return a !== null && a[0] === b[0] && a[1] === b[1];
}

/** The segment row: a small block per kept part of the clip (split at
 * scene edges too), labeled with how its scene is framed (the label is
 * dropped, leaving the tooltip, when the block is too narrow for it);
 * clicking one selects it (Delete then cuts it). */
export function TimelineSegments({
  view,
  parts,
  selected,
  labelAt,
  width = 0,
  onSelect,
}: TimelineSegmentsProps) {
  return (
    <div aria-label="Segments" className="relative h-5">
      {parts.map((part) => {
        const span = spanPercent(part[0], part[1], view);
        const active = same(selected, part);
        const label = labelAt(part);
        const fits = labelFits(label, (span.width / 100) * width);
        return (
          <button
            key={`${part[0]}-${part[1]}`}
            type="button"
            aria-pressed={active}
            aria-label={`Segment ${formatTimecode(part[0])} - ${formatTimecode(part[1])}`}
            title={label}
            onClick={() => onSelect(part)}
            className={cn(
              "absolute inset-y-0 box-border overflow-hidden rounded-sm border text-left text-[10px] leading-[18px] whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
              fits ? "px-1.5" : "px-0",
              active
                ? "border-primary bg-primary/25 text-foreground"
                : "border-border bg-muted/60 text-muted-foreground hover:text-foreground",
            )}
            style={{
              left: `${span.left}%`,
              width: `max(2px, calc(${span.width}% - 1px))`,
            }}
          >
            {fits ? label : null}
          </button>
        );
      })}
    </div>
  );
}
