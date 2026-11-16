import {
  ArrowDownIcon,
  ArrowUpIcon,
  DotsSixVerticalIcon,
  TrashIcon,
} from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { formatTimecode } from "@/lib/format";
import { movedOrder, reorders } from "@/lib/sections";
import type { CutRange } from "@/lib/timeline";
import { cn } from "@/lib/utils";

interface SectionListProps {
  /** The clip's sections in play order, in source seconds. */
  sections: CutRange[];
  /** Ops are not allowed now (unsaved edits, a save or render). */
  locked: boolean;
  /** Play the sections in this order (their current indices). */
  onReorder: (order: number[]) => void;
  onDelete: (index: number) => void;
}

/**
 * The clip's sections in play order. A section drags to another place in
 * the list (or moves with its arrows) to play there; "Delete" drops it
 * unless it is the only one.
 */
export function SectionList({
  sections,
  locked,
  onReorder,
  onDelete,
}: SectionListProps) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);

  const move = (from: number, to: number) => {
    const order = movedOrder(sections.length, from, to);
    if (reorders(order)) onReorder(order);
  };
  const drop = (to: number) => {
    if (dragging !== null) move(dragging, to);
    setDragging(null);
    setOver(null);
  };

  return (
    <ol aria-label="Sections" className="flex flex-col gap-2">
      {sections.map(([start, end], index) => {
        const label = `Section ${index + 1}`;
        return (
          <li
            key={`${start}-${end}`}
            aria-label={label}
            draggable={!locked}
            onDragStart={() => setDragging(index)}
            onDragOver={(event) => {
              event.preventDefault();
              setOver(index);
            }}
            onDrop={(event) => {
              event.preventDefault();
              drop(index);
            }}
            onDragEnd={() => {
              setDragging(null);
              setOver(null);
            }}
            className={cn(
              "flex items-center gap-1 rounded-lg border border-border px-2 py-2",
              dragging === index && "opacity-50",
              over === index && dragging !== index && "border-primary",
            )}
          >
            <DotsSixVerticalIcon
              className="size-4 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <p className="text-body font-medium">{index + 1}</p>
              <p className="truncate text-caption tabular-nums text-muted-foreground">
                {formatTimecode(start)} – {formatTimecode(end)} ·{" "}
                {(end - start).toFixed(1)} s
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`Move ${label} earlier`}
              disabled={locked || index === 0}
              onClick={() => move(index, index - 1)}
            >
              <ArrowUpIcon />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`Move ${label} later`}
              disabled={locked || index === sections.length - 1}
              onClick={() => move(index, index + 1)}
            >
              <ArrowDownIcon />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`Delete ${label}`}
              disabled={locked || sections.length === 1}
              onClick={() => onDelete(index)}
            >
              <TrashIcon />
            </Button>
          </li>
        );
      })}
    </ol>
  );
}
