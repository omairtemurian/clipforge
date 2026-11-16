import { FilmStripIcon, TrashIcon } from "@phosphor-icons/react";
import { mediaThumbnailUrl } from "@/api/mediaLibrary";
import type { MediaItem, TrackItem } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { brollMode } from "@/lib/broll";
import { formatTimecode } from "@/lib/format";
import { choiceClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

interface PlacedBrollProps {
  items: TrackItem[];
  /** The media library, to name each item and credit its source. */
  library: MediaItem[];
  selectedItem: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onRemove: (item: TrackItem) => void;
}

/**
 * The B-roll on the clip: each item's thumbnail, when it plays, whether it
 * is a cutaway or a picture-in-picture, the attribution and license of its
 * source and "Remove".
 */
export function PlacedBroll({
  items,
  library,
  selectedItem,
  disabled,
  onSelect,
  onRemove,
}: PlacedBrollProps) {
  const sorted = [...items].sort((a, b) => a.start - b.start);
  return (
    <ul aria-label="B-roll on the clip" className="flex flex-col gap-2">
      {sorted.map((item) => {
        const media = library.find((each) => each.asset.id === item.asset_id);
        const times = `${formatTimecode(item.start)} – ${formatTimecode(item.end)}`;
        const selected = item.id === selectedItem;
        return (
          <li
            key={item.id}
            className={cn(choiceClass(selected), "flex items-center gap-3")}
          >
            <button
              type="button"
              aria-pressed={selected}
              aria-label={`Select B-roll at ${times}`}
              onClick={() => onSelect(item.id)}
              className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 text-left outline-none"
            >
              <span className="flex h-10 w-16 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted">
                {media?.has_thumbnail ? (
                  <img
                    src={mediaThumbnailUrl(item.asset_id ?? 0)}
                    alt=""
                    className="size-full object-cover"
                  />
                ) : (
                  <FilmStripIcon
                    className="size-4 text-muted-foreground"
                    aria-hidden
                  />
                )}
              </span>
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="flex items-center gap-2 text-caption font-medium tabular-nums">
                  {times}
                  <Pill shape="tag">
                    {brollMode(item) === "pip"
                      ? "Picture-in-picture"
                      : "Cutaway"}
                  </Pill>
                </span>
                {media && (
                  <span className="truncate text-micro text-muted-foreground">
                    {media.asset.attribution} · {media.asset.license}
                  </span>
                )}
              </span>
            </button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              aria-label={`Remove B-roll at ${times}`}
              disabled={disabled}
              onClick={() => onRemove(item)}
              className="size-7 shrink-0"
            >
              <TrashIcon aria-hidden />
            </Button>
          </li>
        );
      })}
    </ul>
  );
}
