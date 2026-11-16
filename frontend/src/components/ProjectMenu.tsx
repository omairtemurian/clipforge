import { useState } from "react";
import { DropdownMenu } from "radix-ui";
import {
  ArrowClockwiseIcon,
  DotsThreeVerticalIcon,
  PencilSimpleIcon,
  TrashIcon,
} from "@phosphor-icons/react";
import { useDeleteProject, useReprocessProject } from "@/api/projects";
import type { Project } from "@/api/types";
import { RenameProjectDialog } from "@/components/RenameProjectDialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { projectName } from "@/lib/format";
import { isArchived } from "@/lib/projectStatus";

const ITEM =
  "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-muted";

/**
 * The kebab menu of a project card: rename it, process a failed one again
 * (it resumes after the last step it finished), or delete it after a
 * confirmation. A running project cannot be deleted (the API refuses).
 */
export function ProjectMenu({ project }: { project: Project }) {
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const name = projectName(project);
  const remove = useDeleteProject();
  const reprocess = useReprocessProject();
  const canReprocess = project.status === "failed" && !isArchived(project);

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label={`Actions for ${name}`}
            className="rounded-full bg-overlay p-1.5 text-muted-foreground backdrop-blur-sm transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            <DotsThreeVerticalIcon className="size-4" aria-hidden />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={4}
            className="z-50 min-w-36 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover"
          >
            <DropdownMenu.Item
              className={ITEM}
              onSelect={() => setDialog("rename")}
            >
              <PencilSimpleIcon className="size-4" aria-hidden />
              Rename
            </DropdownMenu.Item>
            {canReprocess && (
              <DropdownMenu.Item
                className={ITEM}
                disabled={reprocess.isPending}
                onSelect={() => reprocess.mutate(project.id)}
              >
                <ArrowClockwiseIcon className="size-4" aria-hidden />
                Process again
              </DropdownMenu.Item>
            )}
            <DropdownMenu.Item
              className={`${ITEM} text-destructive`}
              disabled={project.status === "running"}
              onSelect={() => setDialog("delete")}
            >
              <TrashIcon className="size-4" aria-hidden />
              Delete
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      {dialog === "rename" && (
        <RenameProjectDialog
          project={project}
          onClose={() => setDialog(null)}
        />
      )}

      {dialog === "delete" && (
        <ConfirmDialog
          title="Delete this project?"
          confirmLabel="Delete"
          destructive
          onConfirm={() => remove.mutate(project.id)}
          onClose={() => setDialog(null)}
        >
          “{name}” and all its clips and files will be removed. This cannot be
          undone.
        </ConfirmDialog>
      )}
    </>
  );
}
