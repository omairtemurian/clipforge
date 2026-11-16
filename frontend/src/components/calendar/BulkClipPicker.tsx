import { useState } from "react";
import { useClips } from "@/api/clips";
import { useProjects } from "@/api/projects";
import type { Project } from "@/api/types";
import { NativeSelect } from "@/components/ui/native-select";
import { clipLength } from "@/lib/clips";
import { formatDuration, projectName } from "@/lib/format";
import { cn } from "@/lib/utils";

interface BulkClipPickerProps {
  chosen: ReadonlySet<number>;
  onChange: (chosen: ReadonlySet<number>) => void;
}

/** The clips of one project with a checkbox each and "Select all". */
function ProjectClips({
  project,
  chosen,
  onChange,
}: BulkClipPickerProps & { project: Project }) {
  const clips = useClips(project);
  const list = clips.data ?? [];
  const all = list.length > 0 && list.every((clip) => chosen.has(clip.id));

  function toggle(ids: number[], on: boolean) {
    const next = new Set(chosen);
    for (const id of ids) {
      if (on) next.add(id);
      else next.delete(id);
    }
    onChange(next);
  }

  if (clips.isPending) {
    return <p className="text-body text-muted-foreground">Loading clips…</p>;
  }
  if (list.length === 0) {
    return (
      <p className="text-body text-muted-foreground">
        This project has no clips.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <label className="flex items-center gap-2 px-2 py-1 text-caption text-muted-foreground">
        <input
          type="checkbox"
          checked={all}
          onChange={() =>
            toggle(
              list.map((clip) => clip.id),
              !all,
            )
          }
          className="size-4 accent-primary"
        />
        Select all
      </label>
      <ul className="flex max-h-56 flex-col gap-1 overflow-y-auto">
        {list.map((clip) => (
          <li key={clip.id}>
            <label
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-lg border border-transparent px-2 py-1.5 hover:bg-muted",
                chosen.has(clip.id) && "border-border bg-muted/60",
              )}
            >
              <input
                type="checkbox"
                checked={chosen.has(clip.id)}
                onChange={() => toggle([clip.id], !chosen.has(clip.id))}
                className="size-4 accent-primary"
              />
              <span className="min-w-0 flex-1 truncate text-body">
                {clip.title}
              </span>
              <span className="text-caption text-muted-foreground tabular-nums">
                {formatDuration(clipLength(clip))}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The bulk scheduler's "Clips": a finished project's clips to post (the
 * choice is kept when another project is picked). */
export function BulkClipPicker({ chosen, onChange }: BulkClipPickerProps) {
  const projects = useProjects();
  const done = (projects.data ?? []).filter(
    (project) => project.status === "done",
  );
  const [projectId, setProjectId] = useState<number | null>(null);
  const project = done.find((each) => each.id === projectId) ?? done[0];

  return (
    <section
      aria-labelledby="bulk-clips"
      className="flex min-w-0 flex-col gap-3"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 id="bulk-clips" className="text-sm font-medium">
          Clips
        </h3>
        <span className="text-caption text-muted-foreground">
          {chosen.size} chosen
        </span>
      </div>
      {projects.isPending ? (
        <p className="text-body text-muted-foreground">Loading projects…</p>
      ) : !project ? (
        <p className="text-body text-muted-foreground">
          No finished project yet. Make clips first.
        </p>
      ) : (
        <>
          <NativeSelect
            aria-label="Project"
            value={project.id}
            onChange={(event) => setProjectId(Number(event.target.value))}
            block
          >
            {done.map((each) => (
              <option key={each.id} value={each.id}>
                {projectName(each)}
              </option>
            ))}
          </NativeSelect>
          <ProjectClips project={project} chosen={chosen} onChange={onChange} />
        </>
      )}
    </section>
  );
}
