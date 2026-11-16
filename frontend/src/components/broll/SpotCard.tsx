import { XIcon } from "@phosphor-icons/react";
import type { BrollSpot, StockClip, TrackItem } from "@/api/types";
import { StockResult } from "@/components/broll/StockResult";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { formatTimecode } from "@/lib/format";
import { placedAt } from "@/lib/broll";

interface SpotCardProps {
  spot: BrollSpot;
  /** The clip's B-roll items: one that plays at the spot is replaced. */
  items: TrackItem[];
  disabled: boolean;
  onChoose: (spot: BrollSpot, stock: StockClip, replace?: TrackItem) => void;
  onSkip: (spot: BrollSpot) => void;
}

/**
 * A spot the AI found for B-roll: when it is said and the sentence, the
 * words searched and the stock videos found. Choosing one puts it on the
 * spot's time, or makes the B-roll already there show it ("Replace");
 * "Skip" drops the spot from the list.
 */
export function SpotCard({
  spot,
  items,
  disabled,
  onChoose,
  onSkip,
}: SpotCardProps) {
  const placed = placedAt(items, spot);
  const label = `${formatTimecode(spot.start)} – ${formatTimecode(spot.end)}`;
  return (
    <li className="flex flex-col gap-3 rounded-xl border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="flex items-center gap-2 text-caption font-medium tabular-nums">
            {label}
            {placed && <Pill tone="success">B-roll placed</Pill>}
          </span>
          <p className="text-body">“{spot.text}”</p>
          <p className="text-caption text-muted-foreground">
            Searched: {spot.query}
          </p>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label={`Skip the spot at ${formatTimecode(spot.start)}`}
          onClick={() => onSkip(spot)}
          className="size-7 shrink-0"
        >
          <XIcon aria-hidden />
        </Button>
      </div>
      {spot.error && (
        <p role="alert" className="text-caption text-destructive">
          {spot.error}
        </p>
      )}
      {!spot.error && spot.results.length === 0 && (
        <p className="text-caption text-muted-foreground">
          No stock video found for this spot.
        </p>
      )}
      {spot.results.length > 0 && (
        <ul
          aria-label={`Stock videos for ${label}`}
          className="grid grid-cols-2 gap-2"
        >
          {spot.results.map((clip) => (
            <StockResult
              key={`${clip.provider}-${clip.provider_id}`}
              clip={clip}
              action={placed ? "Replace" : "Use"}
              disabled={disabled}
              onChoose={() => onChoose(spot, clip, placed)}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
