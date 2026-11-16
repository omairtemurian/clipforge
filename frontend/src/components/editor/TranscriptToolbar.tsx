import {
  CaretDownIcon,
  CaretUpIcon,
  MagicWandIcon,
  MagnifyingGlassIcon,
  XIcon,
} from "@phosphor-icons/react";
import type { KeyboardEvent } from "react";
import { TranscriptDownloads } from "@/components/editor/TranscriptDownloads";
import { Button } from "@/components/ui/button";
import type { TranscriptSearchState } from "@/hooks/useTranscriptSearch";

interface TranscriptToolbarProps {
  search: TranscriptSearchState;
  onCleanup: () => void;
  onSearchOpen: (open: boolean) => void;
  onQuery: (query: string) => void;
  /** Make the next (1) or previous (-1) match active. */
  onStep: (direction: 1 | -1) => void;
  clipId: number;
  projectId: number;
}

/**
 * The transcript's tool row: "Speech cleanup" left; search (Enter / shift
 * +Enter step through the matches, Escape closes) and the transcript and
 * subtitle downloads right.
 */
export function TranscriptToolbar({
  search,
  onCleanup,
  onSearchOpen,
  onQuery,
  onStep,
  clipId,
  projectId,
}: TranscriptToolbarProps) {
  const key = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      onStep(event.shiftKey ? -1 : 1);
    } else if (event.key === "Escape") {
      event.preventDefault();
      onSearchOpen(false);
    }
  };
  const position =
    search.count === 0 ? "0/0" : `${search.active + 1}/${search.count}`;

  return (
    <div className="flex shrink-0 items-center gap-2">
      <Button variant="secondary" onClick={onCleanup}>
        <MagicWandIcon aria-hidden />
        Speech cleanup
      </Button>
      <div className="ml-auto flex min-w-0 items-center gap-1">
        {search.open ? (
          <div className="flex h-8 min-w-0 items-center gap-1 rounded-lg border border-border bg-muted/40 pr-1 pl-2 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
            <MagnifyingGlassIcon
              className="size-4 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <input
              autoFocus
              type="search"
              aria-label="Search the transcript"
              placeholder="Find words"
              value={search.query}
              onChange={(event) => onQuery(event.target.value)}
              onKeyDown={key}
              className="w-36 min-w-0 bg-transparent text-body outline-none placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:hidden"
            />
            {search.query && (
              <span
                aria-label="Matches"
                className="text-caption text-muted-foreground tabular-nums"
              >
                {position}
              </span>
            )}
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Previous match"
              disabled={search.count === 0}
              onClick={() => onStep(-1)}
            >
              <CaretUpIcon aria-hidden />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Next match"
              disabled={search.count === 0}
              onClick={() => onStep(1)}
            >
              <CaretDownIcon aria-hidden />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Close search"
              onClick={() => onSearchOpen(false)}
            >
              <XIcon aria-hidden />
            </Button>
          </div>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Search the transcript"
            title="Search the transcript"
            onClick={() => onSearchOpen(true)}
          >
            <MagnifyingGlassIcon aria-hidden />
          </Button>
        )}
        <TranscriptDownloads clipId={clipId} projectId={projectId} />
      </div>
    </div>
  );
}
