import { useState, type FormEvent } from "react";
import { Dialog } from "radix-ui";
import { useRenameProject } from "@/api/projects";
import type { Project } from "@/api/types";
import { Button } from "@/components/ui/button";
import { projectName } from "@/lib/format";

const TITLE_MAX = 200;

/** A dialog that gives a project a new (not blank) title. */
export function RenameProjectDialog({
  project,
  onClose,
}: {
  project: Project;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(projectName(project));
  const rename = useRenameProject();
  const trimmed = title.trim();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!trimmed) return;
    rename.mutate({ id: project.id, title: trimmed }, { onSuccess: onClose });
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-6 shadow-popover">
          <Dialog.Title className="text-lg font-semibold">
            Rename project
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            The name shown on the project&apos;s card and page.
          </Dialog.Description>
          <form onSubmit={submit} className="mt-4">
            <label htmlFor="project-title" className="text-sm font-medium">
              Title
            </label>
            <input
              id="project-title"
              value={title}
              maxLength={TITLE_MAX}
              onChange={(event) => setTitle(event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <div className="mt-6 flex justify-end gap-2">
              <Dialog.Close asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button type="submit" disabled={!trimmed || rename.isPending}>
                Save
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
