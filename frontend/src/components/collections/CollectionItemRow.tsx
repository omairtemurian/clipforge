import { Link } from "react-router-dom";
import { PencilSimpleIcon, XIcon } from "@phosphor-icons/react";
import type { CollectionItem } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Pill, type PillTone } from "@/components/ui/pill";
import { formatDuration } from "@/lib/format";

const STATUS: Record<
  CollectionItem["clip"]["status"],
  { label: string; tone: PillTone }
> = {
  candidate: { label: "Not rendered", tone: "neutral" },
  rendering: { label: "Rendering", tone: "primary" },
  rendered: { label: "Rendered", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

interface CollectionItemRowProps {
  item: CollectionItem;
  /** Its render is queued but has not started. */
  queued: boolean;
  onRemove: () => void;
}

/** One clip of a collection: its title, span, score and status. */
export function CollectionItemRow({
  item,
  queued,
  onRemove,
}: CollectionItemRowProps) {
  const { clip } = item;
  const status = queued
    ? { label: "Queued", tone: "primary" as const }
    : STATUS[clip.status];
  return (
    <li className="flex items-center gap-3 rounded-xl border border-border px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-body font-medium">{clip.title}</p>
        <p className="text-caption text-muted-foreground">
          {formatDuration(clip.start)}–{formatDuration(clip.end)} · score{" "}
          {clip.overall}
        </p>
      </div>
      <Pill tone={status.tone}>{status.label}</Pill>
      <Button asChild size="icon" variant="ghost">
        <Link to={`/clips/${clip.id}`} aria-label={`Edit ${clip.title}`}>
          <PencilSimpleIcon aria-hidden />
        </Link>
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label={`Remove ${clip.title} from the collection`}
        onClick={onRemove}
      >
        <XIcon aria-hidden />
      </Button>
    </li>
  );
}
