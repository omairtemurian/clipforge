import { useState } from "react";
import {
  DownloadSimpleIcon,
  FilmSlateIcon,
  PencilSimpleIcon,
  TrashIcon,
} from "@phosphor-icons/react";
import {
  collectionZipUrl,
  useCollection,
  useDeleteCollection,
  useRemoveFromCollection,
  useRenderCollectionClips,
} from "@/api/collections";
import type { CollectionClip } from "@/api/types";
import { CollectionItemRow } from "@/components/collections/CollectionItemRow";
import { RenameCollectionDialog } from "@/components/collections/RenameCollectionDialog";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { clipCountLabel } from "@/lib/format";

interface CollectionPanelProps {
  id: number;
  /** Clips of it whose renders were queued before it opened. */
  queued?: number[];
  onDeleted: () => void;
}

/**
 * One collection: its clips in order with their status, renaming,
 * deleting (asked first), rendering the clips not rendered yet and the
 * zip of the rendered ones.
 */
export function CollectionPanel({
  id,
  queued: queuedBefore = [],
  onDeleted,
}: CollectionPanelProps) {
  // The clips whose renders were queued, with their status then: one is
  // waiting for its render until its status changes.
  const [queued, setQueued] = useState<ReadonlyMap<number, string>>(
    () => new Map(queuedBefore.map((clipId) => [clipId, "candidate"])),
  );
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const waiting = (clip: CollectionClip) => queued.get(clip.id) === clip.status;
  const collection = useCollection(id, ({ items }) =>
    items.some(({ clip }) => clip.status === "rendering" || waiting(clip)),
  );
  const items = collection.data?.items;

  const [seen, setSeen] = useState(items);
  if (items !== seen) {
    setSeen(items);
    const started = (items ?? []).filter(
      ({ clip }) => queued.has(clip.id) && !waiting(clip),
    );
    if (started.length > 0) {
      const next = new Map(queued);
      for (const { clip } of started) next.delete(clip.id);
      setQueued(next);
    }
  }
  const remove = useRemoveFromCollection(id);
  const destroy = useDeleteCollection();
  const render = useRenderCollectionClips();

  if (collection.isPending) return <Skeleton className="h-64 rounded-xl" />;
  if (collection.isError) {
    return (
      <p className="text-body text-muted-foreground">
        Could not load this collection.
      </p>
    );
  }
  const detail = collection.data;
  const missing = detail.items
    .map(({ clip }) => clip)
    .filter(
      (clip) =>
        (clip.status === "candidate" || clip.status === "failed") &&
        !waiting(clip),
    );
  const rendered = detail.items.filter(
    ({ clip }) => clip.status === "rendered",
  ).length;

  function renderMissing() {
    render.mutate(
      missing.map((clip) => clip.id),
      {
        onSuccess: () =>
          setQueued(
            new Map([
              ...queued,
              ...missing.map((clip): [number, string] => [
                clip.id,
                clip.status,
              ]),
            ]),
          ),
      },
    );
  }

  return (
    <section aria-label={detail.name} className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-section font-semibold">{detail.name}</h2>
          <p className="text-body text-muted-foreground">
            {clipCountLabel(detail.items.length)} · {rendered} rendered
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Rename collection"
            onClick={() => setDialog("rename")}
          >
            <PencilSimpleIcon aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Delete collection"
            onClick={() => setDialog("delete")}
          >
            <TrashIcon aria-hidden />
          </Button>
          {missing.length > 0 && (
            <Button
              variant="outline"
              disabled={render.isPending}
              onClick={renderMissing}
            >
              <FilmSlateIcon aria-hidden />
              Render {clipCountLabel(missing.length)}
            </Button>
          )}
          {rendered > 0 ? (
            <Button asChild>
              <a href={collectionZipUrl(id)}>
                <DownloadSimpleIcon aria-hidden />
                Download zip
              </a>
            </Button>
          ) : (
            <Button disabled>
              <DownloadSimpleIcon aria-hidden />
              Download zip
            </Button>
          )}
        </div>
      </header>
      {detail.items.length === 0 ? (
        <EmptyState icon={FilmSlateIcon} title="No clips yet">
          Add clips from a project&apos;s gallery or from moments found in the
          Media library.
        </EmptyState>
      ) : (
        <ol aria-label="Clips" className="space-y-2">
          {detail.items.map((item) => (
            <CollectionItemRow
              key={item.id}
              item={item}
              queued={waiting(item.clip)}
              onRemove={() => remove.mutate(item.clip.id)}
            />
          ))}
        </ol>
      )}
      {rendered < detail.items.length && rendered > 0 && (
        <p className="text-caption text-muted-foreground">
          The zip holds the rendered clips; manifest.json lists the others.
        </p>
      )}
      {dialog === "rename" && (
        <RenameCollectionDialog
          id={id}
          name={detail.name}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "delete" && (
        <ConfirmDialog
          title="Delete this collection?"
          confirmLabel="Delete"
          destructive
          onConfirm={() => destroy.mutate(id, { onSuccess: onDeleted })}
          onClose={() => setDialog(null)}
        >
          “{detail.name}” will be removed. Its clips stay in their projects.
        </ConfirmDialog>
      )}
    </section>
  );
}
