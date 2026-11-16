import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { FolderPlusIcon, MagnifyingGlassIcon } from "@phosphor-icons/react";
import { useProjects } from "@/api/projects";
import {
  clipFromMoment,
  useClipFromMoment,
  useLibrarySearch,
} from "@/api/search";
import type { SearchHit } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { AddToCollectionDialog } from "@/components/library/AddToCollectionDialog";
import { LibrarySearchForm } from "@/components/library/LibrarySearchForm";
import { MomentPreview } from "@/components/library/MomentPreview";
import { SearchHitRow } from "@/components/library/SearchHitRow";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DEFAULT_MOMENT_LENGTH,
  hitKey,
  resultsCollectionName,
} from "@/lib/library";
import { isArchived } from "@/lib/projectStatus";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

function momentWord(count: number): string {
  return `${count} ${count === 1 ? "moment" : "moments"}`;
}

/**
 * Search what was said in every processed video (?q=, ?project=): play a
 * moment found from its start, make a clip of it, or put the selected
 * moments as clips in a collection to export them together.
 */
export function LibraryPage() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const projectParam = params.get("project");
  const projectId = projectParam ? Number(projectParam) : null;
  const [length, setLength] = useState(DEFAULT_MOMENT_LENGTH);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [playing, setPlaying] = useState<SearchHit | null>(null);
  const [made, setMade] = useState<ReadonlyMap<string, number>>(new Map());
  const [exporting, setExporting] = useState(false);
  const projects = useProjects();
  const search = useLibrarySearch({ q: query, projectId });
  const makeClip = useClipFromMoment();

  const archived = useMemo(
    () =>
      new Set(
        (projects.data ?? []).filter(isArchived).map((project) => project.id),
      ),
    [projects.data],
  );
  const searchable = (projects.data ?? []).filter((p) => p.status === "done");
  const hits = search.data ?? [];
  const picked = hits.filter((hit) => selected.has(hitKey(hit)));

  function setParam(name: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
    setSelected(new Set());
  }

  function select(hit: SearchHit, on: boolean) {
    const next = new Set(selected);
    if (on) next.add(hitKey(hit));
    else next.delete(hitKey(hit));
    setSelected(next);
  }

  function remember(hit: SearchHit, clipId: number) {
    setMade((current) => new Map(current).set(hitKey(hit), clipId));
  }

  /** The clips of the picked moments, made (and queued to render) as needed. */
  async function pickedClipIds(): Promise<number[]> {
    const ids: number[] = [];
    for (const hit of picked) {
      let id = made.get(hitKey(hit));
      if (id === undefined) {
        id = (
          await clipFromMoment({
            projectId: hit.project_id,
            at: hit.start,
            length,
          })
        ).id;
        remember(hit, id);
      }
      ids.push(id);
    }
    return ids;
  }

  let results;
  if (!query) {
    results = (
      <EmptyState icon={MagnifyingGlassIcon} title="Search your videos">
        Find the moments where something was said, in every processed video.
      </EmptyState>
    );
  } else if (search.isPending) {
    results = (
      <div className="space-y-3" aria-hidden>
        {[0, 1, 2].map((index) => (
          <Skeleton key={index} className="h-28 rounded-xl" />
        ))}
      </div>
    );
  } else if (search.isError) {
    results = (
      <p className="py-12 text-center text-body text-muted-foreground">
        Could not search the transcripts.
      </p>
    );
  } else if (hits.length === 0) {
    results = (
      <EmptyState icon={MagnifyingGlassIcon} title="No moments found">
        Nothing said matches “{query}”. Try other words.
      </EmptyState>
    );
  } else {
    results = (
      <ul className="space-y-3" aria-label="Moments found">
        {hits.map((hit) => {
          const key = hitKey(hit);
          return (
            <SearchHitRow
              key={key}
              hit={hit}
              selected={selected.has(key)}
              playing={playing !== null && hitKey(playing) === key}
              archived={archived.has(hit.project_id)}
              clipId={made.get(key) ?? null}
              making={
                makeClip.isPending &&
                makeClip.variables.projectId === hit.project_id &&
                makeClip.variables.at === hit.start
              }
              onSelect={(on) => select(hit, on)}
              onPlay={() => setPlaying(hit)}
              onMakeClip={() =>
                makeClip.mutate(
                  { projectId: hit.project_id, at: hit.start, length },
                  { onSuccess: (clip) => remember(hit, clip.id) },
                )
              }
            />
          );
        })}
      </ul>
    );
  }

  return (
    <>
      <PageHeader
        title="Media library"
        width="wide"
        description="Search the transcripts of every video and turn the moments into clips."
      />
      <div className={cn(pageColumn("wide"), "space-y-6 pb-section")}>
        <LibrarySearchForm
          key={query}
          query={query}
          projectId={projectId}
          length={length}
          projects={searchable}
          onSearch={(q) => setParam("q", q)}
          onProjectChange={(id) => setParam("project", id ? String(id) : null)}
          onLengthChange={setLength}
        />
        {hits.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 text-body text-muted-foreground">
            <span>
              {momentWord(hits.length)} found
              {picked.length > 0 && ` · ${picked.length} selected`}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setSelected(
                  new Set(
                    hits
                      .filter((hit) => !archived.has(hit.project_id))
                      .map(hitKey),
                  ),
                )
              }
            >
              Select all
            </Button>
            <Button
              className="ml-auto"
              disabled={picked.length === 0}
              onClick={() => setExporting(true)}
            >
              <FolderPlusIcon aria-hidden />
              Export to collection
            </Button>
          </div>
        )}
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
          <section aria-label="Results">{results}</section>
          <aside className="lg:sticky lg:top-6" aria-label="Preview">
            <MomentPreview hit={playing} />
          </aside>
        </div>
      </div>
      {exporting && (
        <AddToCollectionDialog
          what={momentWord(picked.length)}
          suggestedName={resultsCollectionName(query)}
          clipIds={pickedClipIds}
          rendersQueued
          onClose={() => setExporting(false)}
        />
      )}
    </>
  );
}
