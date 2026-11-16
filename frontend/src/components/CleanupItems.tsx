import { PauseIcon, RepeatIcon, WaveformIcon } from "@phosphor-icons/react";
import type { CleanupSuggestion } from "@/api/types";
import { suggestionLabel } from "@/lib/cleanup";
import { formatTimecode } from "@/lib/format";
import { formatPause } from "@/lib/transcriptView";

interface CleanupItemsProps {
  items: CleanupSuggestion[];
  /** The indexes of the items the user left unchecked. */
  unchecked: ReadonlySet<number>;
  disabled: boolean;
  onToggle: (index: number) => void;
}

const ICONS = { filler: WaveformIcon, pause: PauseIcon, bad_take: RepeatIcon };

/** The items that speech cleanup would remove, each with a checkbox
 * (checked unless its index is in unchecked), its time and its length. */
export function CleanupItems({
  items,
  unchecked,
  disabled,
  onToggle,
}: CleanupItemsProps) {
  return (
    <ul aria-label="What will be removed" className="flex flex-col gap-2">
      {items.map((item, index) => {
        const Icon = ICONS[item.kind];
        return (
          <li key={`${item.start}-${item.end}`}>
            <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2 text-body transition-colors hover:bg-muted/60 has-disabled:cursor-default has-disabled:opacity-60">
              <input
                type="checkbox"
                checked={!unchecked.has(index)}
                disabled={disabled}
                onChange={() => onToggle(index)}
                className="size-4 shrink-0 accent-primary"
              />
              <Icon
                className="size-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <span className="min-w-0 flex-1 truncate font-medium">
                {suggestionLabel(item)}
              </span>
              <span className="shrink-0 text-caption text-muted-foreground tabular-nums">
                {formatTimecode(item.start)} ·{" "}
                {formatPause(item.end - item.start)}
              </span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}
