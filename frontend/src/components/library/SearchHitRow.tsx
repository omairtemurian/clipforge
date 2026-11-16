import { Link } from "react-router-dom";
import { FilmSlateIcon, PlayIcon, ScissorsIcon } from "@phosphor-icons/react";
import type { SearchHit } from "@/api/types";
import { Button } from "@/components/ui/button";
import { formatDuration } from "@/lib/format";
import { highlightParts } from "@/lib/library";
import { cn } from "@/lib/utils";

interface SearchHitRowProps {
  hit: SearchHit;
  selected: boolean;
  playing: boolean;
  /** The hit's project was archived: its source video is gone. */
  archived: boolean;
  /** The clip made from this moment, once made. */
  clipId: number | null;
  making: boolean;
  onSelect: (selected: boolean) => void;
  onPlay: () => void;
  onMakeClip: () => void;
}

/**
 * One moment found: its project and time, the transcript text with the
 * matched words marked, and play / make a clip / open the clip.
 */
export function SearchHitRow({
  hit,
  selected,
  playing,
  archived,
  clipId,
  making,
  onSelect,
  onPlay,
  onMakeClip,
}: SearchHitRowProps) {
  const at = formatDuration(hit.start);
  const label = `${hit.project_title} at ${at}`;
  return (
    <li
      className={cn(
        "flex gap-3 rounded-xl border border-border p-4 transition-colors",
        playing && "border-primary bg-primary/5",
      )}
    >
      <input
        type="checkbox"
        aria-label={`Select ${label}`}
        checked={selected}
        disabled={archived}
        onChange={(event) => onSelect(event.target.checked)}
        className="mt-1 size-4 accent-primary"
      />
      <div className="min-w-0 flex-1">
        <p className="text-caption text-muted-foreground">
          <Link
            to={`/projects/${hit.project_id}`}
            className="font-medium text-foreground hover:underline"
          >
            {hit.project_title}
          </Link>{" "}
          · {at}
          {archived && " · archived"}
        </p>
        <p className="mt-1 text-body">
          {highlightParts(hit.text, hit.highlights).map((part, index) =>
            part.marked ? (
              <mark
                key={index}
                className="rounded-sm bg-primary/20 px-0.5 text-primary-ink"
              >
                {part.text}
              </mark>
            ) : (
              <span key={index}>{part.text}</span>
            ),
          )}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={archived}
            onClick={onPlay}
            aria-label={`Play ${label}`}
          >
            <PlayIcon aria-hidden />
            Play from {at}
          </Button>
          {clipId === null ? (
            <Button
              size="sm"
              variant="secondary"
              disabled={archived || making}
              onClick={onMakeClip}
              aria-label={`Make clip of ${label}`}
            >
              <ScissorsIcon aria-hidden />
              {making ? "Making clip…" : "Make clip"}
            </Button>
          ) : (
            <Button size="sm" variant="secondary" asChild>
              <Link to={`/clips/${clipId}`}>
                <FilmSlateIcon aria-hidden />
                Open clip
              </Link>
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}
