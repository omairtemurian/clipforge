import { Link } from "react-router-dom";
import { ArchiveIcon, BroomIcon } from "@phosphor-icons/react";
import type { ProjectStorage } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { formatBytes } from "@/lib/format";

/** What a storage action is asked about: the project and the action. */
export interface StorageAsk {
  project: ProjectStorage;
  action: "cleanup" | "archive";
}

interface StorageRowProps {
  project: ProjectStorage;
  onAsk: (ask: StorageAsk) => void;
}

function idle(project: ProjectStorage): boolean {
  return project.status === "done" || project.status === "failed";
}

/** One project's disk use and its "Clean up" and "Archive" buttons. */
export function StorageRow({ project, onAsk }: StorageRowProps) {
  const archived = project.archived_at !== null;
  const busy = !idle(project);
  return (
    <tr className="border-b border-border last:border-0">
      <td className="max-w-64 py-3 pr-4">
        <Link
          to={`/projects/${project.project_id}`}
          className="block truncate font-medium hover:underline"
        >
          {project.title}
        </Link>
        {archived && <Pill className="mt-1">Archived</Pill>}
        {busy && <Pill className="mt-1">Processing</Pill>}
      </td>
      <td className="py-3 pr-4 tabular-nums">
        {formatBytes(project.source_bytes)}
      </td>
      <td className="py-3 pr-4 tabular-nums">
        {formatBytes(project.work_bytes)}
      </td>
      <td className="py-3 pr-4 tabular-nums">
        {formatBytes(project.output_bytes)}
      </td>
      <td className="py-3 pr-4 font-medium tabular-nums">
        {formatBytes(project.total_bytes)}
      </td>
      <td className="py-3">
        <div className="flex justify-end gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={busy || project.cleanable_bytes === 0}
            onClick={() => onAsk({ project, action: "cleanup" })}
            aria-label={`Clean up ${project.title}`}
          >
            <BroomIcon aria-hidden />
            Clean up
            {project.cleanable_bytes > 0 &&
              ` ${formatBytes(project.cleanable_bytes)}`}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy || archived}
            onClick={() => onAsk({ project, action: "archive" })}
            aria-label={`Archive ${project.title}`}
          >
            <ArchiveIcon aria-hidden />
            Archive
          </Button>
        </div>
      </td>
    </tr>
  );
}
