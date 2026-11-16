import { FilmSlateIcon, MagnifyingGlassMinusIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { apiUrl } from "@/api/client";
import {
  useClips,
  useDeleteClip,
  useRenderClips,
  useRenderingClipIds,
} from "@/api/clips";
import type { Clip, Project } from "@/api/types";
import { ClipCard } from "@/components/ClipCard";
import { GalleryActions } from "@/components/GalleryActions";
import { GalleryToolbar } from "@/components/GalleryToolbar";
import { ProjectCampaignSelect } from "@/components/ProjectCampaignSelect";
import { StatusPill } from "@/components/ProjectCard";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { groupVariants, useRenderVariants } from "@/features/proedit";
import { visibleClips, type ClipFilter } from "@/lib/clips";
import { clipCountLabel, formatDate, projectName } from "@/lib/format";
import { isArchived } from "@/lib/projectStatus";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

const GRID =
  "grid grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-x-4 gap-y-8";
const SKELETONS = 6;

const NO_FILTER: ClipFilter = { sort: "score", minScore: 0, query: "" };

/** The clips of a finished project: a toolbar and a grid of 9:16 cards. */
export function Gallery({ project }: { project: Project }) {
  const [picked, setPicked] = useState<number | null>(null);
  const clips = useClips(project, picked ?? undefined);
  const renderingIds = useRenderingClipIds(project);
  const render = useRenderClips(project.id);
  const renderVariants = useRenderVariants();
  const remove = useDeleteClip(project.id);
  const [filter, setFilter] = useState(NO_FILTER);

  /** Queue the renders of targets: a Pro Edit variant renders its plan
   * (the v1 render would replace its video), any other clip as usual. */
  function renderClips(targets: Clip[]) {
    const variants = targets.filter((clip) => clip.variant === "pro_edit");
    const others = targets.filter((clip) => clip.variant !== "pro_edit");
    if (others.length > 0) render.mutate(others.map((clip) => clip.id));
    if (variants.length > 0) {
      renderVariants.mutate(variants.map((clip) => clip.id));
    }
  }

  function removeClip(clip: Clip) {
    if (window.confirm(`Remove "${clip.title}"? This deletes its files too.`)) {
      remove.mutate(clip.id);
    }
  }

  const all = clips.data ?? [];
  const shown = groupVariants(visibleClips(all, filter));
  const isBusy = (clip: Clip) =>
    renderingIds.has(clip.id) || clip.status === "rendering";
  const waiting = all.some(isBusy);
  const posterUrl = project.thumbnail_path
    ? apiUrl(`/media/${project.id}/thumbnail`)
    : null;

  let body;
  if (clips.isPending) {
    body = (
      <div className={GRID}>
        {Array.from({ length: SKELETONS }, (_, index) => (
          <div key={index} aria-hidden>
            <Skeleton className="aspect-[9/16] rounded-xl" />
            <Skeleton className="mt-3 h-8 w-1/2 rounded-lg" />
            <Skeleton className="mt-2 h-4 w-3/4" />
          </div>
        ))}
      </div>
    );
  } else if (clips.isError) {
    body = (
      <div className="flex flex-col items-center gap-4 py-12 text-body text-muted-foreground">
        <p>Could not load the clips.</p>
        <Button variant="outline" onClick={() => void clips.refetch()}>
          Try again
        </Button>
      </div>
    );
  } else if (all.length === 0) {
    body = (
      <EmptyState icon={FilmSlateIcon} title="No clips found">
        ClipForge did not find a moment worth a short in this video. Try another
        genre or a longer timeframe.
      </EmptyState>
    );
  } else if (shown.length === 0) {
    body = (
      <EmptyState
        icon={MagnifyingGlassMinusIcon}
        title="No clips match"
        action={
          <Button variant="outline" onClick={() => setFilter(NO_FILTER)}>
            Clear filters
          </Button>
        }
      >
        Lower the minimum score or change the search to see more clips.
      </EmptyState>
    );
  } else {
    body = (
      <ul className={GRID}>
        {shown.map((clip) => (
          <li key={clip.id} className="min-w-0">
            <ClipCard
              clip={clip}
              posterUrl={posterUrl}
              rendering={isBusy(clip)}
              onRender={(target) => renderClips([target])}
              onRemove={removeClip}
            />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className={cn(pageColumn("wide"), "pt-8 pb-section")}>
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="truncate text-title">{projectName(project)}</h1>
            <StatusPill status={project.status} />
            {isArchived(project) && <Pill>Archived</Pill>}
          </div>
          <p className="mt-1 text-body text-muted-foreground">
            {clips.data ? `${clipCountLabel(all.length)} · ` : ""}
            {formatDate(project.created_at)}
          </p>
          <ProjectCampaignSelect project={project} />
        </div>
        <GalleryActions
          project={project}
          resultSet={picked ?? project.result_set}
          onResultSetChange={setPicked}
        />
      </header>
      {all.length > 0 && (
        <div className="sticky top-0 z-10 -mx-page mb-6 border-b border-border bg-background/90 px-page py-3 backdrop-blur">
          <GalleryToolbar
            filter={filter}
            onFilterChange={setFilter}
            projectId={project.id}
            allRendered={all.every((clip) => clip.status === "rendered")}
            rendering={waiting || render.isPending || renderVariants.isPending}
            onRenderAll={() =>
              renderClips(all.filter((clip) => clip.status !== "rendered"))
            }
            shownClipIds={shown.map((clip) => clip.id)}
            projectName={projectName(project)}
          />
        </div>
      )}
      <h2 className="mb-4 text-section text-muted-foreground">
        Clips{clips.data ? ` (${shown.length})` : ""}
      </h2>
      {body}
    </div>
  );
}
