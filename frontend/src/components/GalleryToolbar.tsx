import {
  CircleNotchIcon,
  DownloadSimpleIcon,
  MagnifyingGlassIcon,
} from "@phosphor-icons/react";
import { Slider } from "radix-ui";
import { apiUrl } from "@/api/client";
import { AddClipsToCollection } from "@/components/library/AddClipsToCollection";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import type { ClipFilter, ClipSort } from "@/lib/clips";
import { cn } from "@/lib/utils";

const MAX_SCORE = 99;

interface GalleryToolbarProps {
  filter: ClipFilter;
  onFilterChange: (filter: ClipFilter) => void;
  projectId: number;
  /** Every clip of the project is rendered, so the zip can be downloaded. */
  allRendered: boolean;
  /** Some clip is being rendered. */
  rendering: boolean;
  onRenderAll: () => void;
  /** The clips shown, which "Add to collection" adds. */
  shownClipIds: number[];
  /** The name a new collection of them starts with. */
  projectName: string;
}

/** The "Download all" button: the zip once every clip is rendered, else it renders the rest. */
function DownloadAll({
  projectId,
  allRendered,
  rendering,
  onRenderAll,
}: Omit<
  GalleryToolbarProps,
  "filter" | "onFilterChange" | "shownClipIds" | "projectName"
>) {
  if (allRendered) {
    return (
      <Button asChild variant="outline">
        <a href={apiUrl(`/projects/${projectId}/download.zip`)}>
          <DownloadSimpleIcon aria-hidden />
          Download all
        </a>
      </Button>
    );
  }
  return (
    <Button variant="outline" disabled={rendering} onClick={onRenderAll}>
      {rendering ? (
        <CircleNotchIcon className="animate-spin" aria-hidden />
      ) : (
        <DownloadSimpleIcon aria-hidden />
      )}
      {rendering ? "Rendering…" : "Download all"}
    </Button>
  );
}

/**
 * Search, sort, minimum score, "Add to collection" (the clips shown) and
 * "Download all" above the clip grid.
 */
export function GalleryToolbar({
  filter,
  onFilterChange,
  shownClipIds,
  projectName,
  ...download
}: GalleryToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <div className="relative min-w-52 flex-1 sm:max-w-xs">
        <MagnifyingGlassIcon
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <input
          type="search"
          aria-label="Search clips"
          placeholder="Search clips…"
          value={filter.query}
          onChange={(event) =>
            onFilterChange({ ...filter, query: event.target.value })
          }
          className={cn(INPUT, "h-9 pl-9")}
        />
      </div>
      <label className="flex items-center gap-2 text-body text-muted-foreground">
        Sort by
        <NativeSelect
          value={filter.sort}
          onChange={(event) =>
            onFilterChange({ ...filter, sort: event.target.value as ClipSort })
          }
        >
          <option value="score">Best score</option>
          <option value="duration">Shortest</option>
        </NativeSelect>
      </label>
      <div className="flex items-center gap-3 text-body text-muted-foreground">
        <span id="min-score-label">Min score</span>
        <Slider.Root
          min={0}
          max={MAX_SCORE}
          step={1}
          value={[filter.minScore]}
          onValueChange={([minScore]) =>
            onFilterChange({ ...filter, minScore })
          }
          className="relative flex h-5 w-32 touch-none items-center select-none"
        >
          <Slider.Track className="relative h-1.5 grow overflow-hidden rounded-full bg-muted">
            <Slider.Range className="absolute h-full bg-primary" />
          </Slider.Track>
          <Slider.Thumb
            aria-labelledby="min-score-label"
            className="block size-4 rounded-full border-2 border-primary bg-background shadow-card transition-[box-shadow] outline-none hover:ring-4 hover:ring-ring/20 focus-visible:ring-4 focus-visible:ring-ring/40"
          />
        </Slider.Root>
        <span className="w-6 text-foreground tabular-nums">
          {filter.minScore}
        </span>
      </div>
      <div className="ml-auto flex gap-2">
        <AddClipsToCollection
          clipIds={shownClipIds}
          suggestedName={projectName}
        />
        <DownloadAll {...download} />
      </div>
    </div>
  );
}
