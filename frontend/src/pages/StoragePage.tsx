import { useState } from "react";
import { HardDrivesIcon } from "@phosphor-icons/react";
import { useStorage, useStorageAction } from "@/api/storage";
import { PageHeader } from "@/components/PageHeader";
import { SettingsTabs } from "@/components/appsettings/SettingsTabs";
import { StorageRow, type StorageAsk } from "@/components/storage/StorageRow";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes } from "@/lib/format";
import { cardClass, pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** The question a storage action asks before it deletes files. */
function AskText({ ask }: { ask: StorageAsk }) {
  if (ask.action === "cleanup") {
    return (
      <>
        Deletes the working files of “{ask.project.title}” that can be made
        again (extracted audio, face cache, editor previews
        {ask.project.status === "done" && ", the uploaded copy of the video"}
        ), freeing about {formatBytes(ask.project.cleanable_bytes)}. Clips and
        exports stay.
      </>
    );
  }
  return (
    <>
      Deletes the source video and the working files of “{ask.project.title}”.
      Rendered clips, exports and the transcript stay and can still be
      downloaded and searched, but its clips can no longer be edited or rendered
      again. This cannot be undone.
    </>
  );
}

/**
 * Settings → Storage: the disk use of every project, largest first, the
 * free space, and cleaning up or archiving a project after a confirmation.
 */
export function StoragePage() {
  const storage = useStorage();
  const cleanup = useStorageAction("cleanup");
  const archive = useStorageAction("archive");
  const [ask, setAsk] = useState<StorageAsk | null>(null);

  let body;
  if (storage.isPending) {
    body = <Skeleton className="h-48 rounded-xl" />;
  } else if (storage.isError) {
    body = (
      <p className="text-body text-muted-foreground">
        Could not read the disk use.
      </p>
    );
  } else if (storage.data.projects.length === 0) {
    body = (
      <EmptyState icon={HardDrivesIcon} title="No projects yet">
        The disk use of each project shows here.
      </EmptyState>
    );
  } else {
    body = (
      <div className={cn(cardClass(), "overflow-x-auto px-4")}>
        <table className="w-full text-left text-body">
          <thead className="text-caption text-muted-foreground">
            <tr className="border-b border-border">
              <th className="py-2 pr-4 font-medium">Project</th>
              <th className="py-2 pr-4 font-medium">Source</th>
              <th className="py-2 pr-4 font-medium">Work files</th>
              <th className="py-2 pr-4 font-medium">Clips &amp; exports</th>
              <th className="py-2 pr-4 font-medium">Total</th>
              <th className="py-2 text-right font-medium">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {storage.data.projects.map((project) => (
              <StorageRow
                key={project.project_id}
                project={project}
                onAsk={setAsk}
              />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Storage"
        width="wide"
        description="How much disk each project uses, and freeing it."
      />
      <div className={cn(pageColumn("wide"), "pb-10")}>
        <div className="flex flex-col gap-6">
          <SettingsTabs />
          {storage.data && (
            <dl className="flex flex-wrap gap-x-8 gap-y-2 text-body">
              <div>
                <dt className="text-caption text-muted-foreground">Used</dt>
                <dd className="text-section font-semibold">
                  {formatBytes(storage.data.total_bytes)}
                </dd>
              </div>
              <div>
                <dt className="text-caption text-muted-foreground">Free</dt>
                <dd className="text-section font-semibold">
                  {formatBytes(storage.data.free_bytes)}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-caption text-muted-foreground">
                  Data folder
                </dt>
                <dd className="truncate font-mono text-caption leading-6">
                  {storage.data.data_dir}
                </dd>
              </div>
            </dl>
          )}
          {body}
        </div>
      </div>
      {ask && (
        <ConfirmDialog
          title={
            ask.action === "cleanup"
              ? "Clean up this project?"
              : "Archive this project?"
          }
          confirmLabel={ask.action === "cleanup" ? "Clean up" : "Archive"}
          destructive={ask.action === "archive"}
          onConfirm={() =>
            (ask.action === "cleanup" ? cleanup : archive).mutate(
              ask.project.project_id,
            )
          }
          onClose={() => setAsk(null)}
        >
          <AskText ask={ask} />
        </ConfirmDialog>
      )}
    </>
  );
}
