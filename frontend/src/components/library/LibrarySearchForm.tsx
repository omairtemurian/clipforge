import { useState, type FormEvent } from "react";
import { MagnifyingGlassIcon } from "@phosphor-icons/react";
import type { Project } from "@/api/types";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { projectName } from "@/lib/format";
import { MOMENT_LENGTHS } from "@/lib/library";
import { cn } from "@/lib/utils";

interface LibrarySearchFormProps {
  query: string;
  projectId: number | null;
  length: number;
  projects: Project[];
  onSearch: (query: string) => void;
  onProjectChange: (projectId: number | null) => void;
  onLengthChange: (length: number) => void;
}

/**
 * The Library's search box (searched on submit), the project to search in
 * and the length of the clips made from the moments found.
 */
export function LibrarySearchForm({
  query,
  projectId,
  length,
  projects,
  onSearch,
  onProjectChange,
  onLengthChange,
}: LibrarySearchFormProps) {
  const [draft, setDraft] = useState(query);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSearch(draft.trim());
  }

  return (
    <form
      role="search"
      onSubmit={submit}
      className="flex flex-wrap items-center gap-x-4 gap-y-3"
    >
      <div className="relative min-w-60 flex-1">
        <MagnifyingGlassIcon
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <input
          type="search"
          aria-label="Search transcripts"
          placeholder="Search what was said in every video…"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className={cn(INPUT, "h-9 pl-9")}
        />
      </div>
      <label className="flex items-center gap-2 text-body text-muted-foreground">
        In
        <NativeSelect
          aria-label="Project"
          value={projectId ?? ""}
          onChange={(event) =>
            onProjectChange(
              event.target.value === "" ? null : Number(event.target.value),
            )
          }
        >
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {projectName(project)}
            </option>
          ))}
        </NativeSelect>
      </label>
      <label className="flex items-center gap-2 text-body text-muted-foreground">
        Clip length
        <NativeSelect
          aria-label="Clip length"
          value={length}
          onChange={(event) => onLengthChange(Number(event.target.value))}
        >
          {MOMENT_LENGTHS.map((seconds) => (
            <option key={seconds} value={seconds}>
              {seconds}s
            </option>
          ))}
        </NativeSelect>
      </label>
      <Button type="submit" disabled={!draft.trim()}>
        Search
      </Button>
    </form>
  );
}
