import { ArrowSquareOutIcon, ClockIcon } from "@phosphor-icons/react";
import { useProject } from "@/api/projects";
import { freshnessLabel } from "@/lib/drafts";

/** The source video of a draft's clip: a link to it and how long ago it was
 * uploaded (freshness matters for campaigns). */
export function DraftSource({ projectId }: { projectId: number }) {
  const project = useProject(projectId);
  if (!project.data) return null;
  const { source_url: url, source_published_at: published } = project.data;
  const freshness = freshnessLabel(published);

  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-muted-foreground">
      {freshness && (
        <span className="inline-flex items-center gap-1">
          <ClockIcon className="size-3.5" aria-hidden />
          {freshness}
        </span>
      )}
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 rounded text-primary-ink outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          Source video
          <ArrowSquareOutIcon className="size-3.5" aria-hidden />
        </a>
      )}
    </p>
  );
}
