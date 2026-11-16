import { useState, type FormEvent } from "react";
import { PlusIcon } from "@phosphor-icons/react";
import { useCollections, useCreateCollection } from "@/api/collections";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { clipCountLabel } from "@/lib/format";
import { COLLECTION_NAME_MAX } from "@/lib/library";
import { cn } from "@/lib/utils";

interface CollectionListProps {
  selectedId: number | null;
  onSelect: (id: number) => void;
}

/** Every collection, to pick one, and a field to make a new one. */
export function CollectionList({ selectedId, onSelect }: CollectionListProps) {
  const collections = useCollections();
  const create = useCreateCollection();
  const [name, setName] = useState("");
  const trimmed = name.trim();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!trimmed) return;
    create.mutate(trimmed, {
      onSuccess: (collection) => {
        setName("");
        onSelect(collection.id);
      },
    });
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="flex gap-2">
        <input
          aria-label="New collection name"
          placeholder="New collection…"
          value={name}
          maxLength={COLLECTION_NAME_MAX}
          onChange={(event) => setName(event.target.value)}
          className={cn(INPUT, "h-9")}
        />
        <Button type="submit" disabled={!trimmed || create.isPending}>
          <PlusIcon aria-hidden />
          Create
        </Button>
      </form>
      {collections.isPending ? (
        <Skeleton className="h-24 rounded-xl" />
      ) : collections.data?.length ? (
        <ul aria-label="Collections" className="space-y-1">
          {collections.data.map((collection) => (
            <li key={collection.id}>
              <button
                type="button"
                aria-current={collection.id === selectedId}
                onClick={() => onSelect(collection.id)}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-body transition-colors hover:bg-muted",
                  collection.id === selectedId &&
                    "bg-muted font-medium text-foreground",
                )}
              >
                <span className="truncate">{collection.name}</span>
                <span className="shrink-0 text-caption text-muted-foreground">
                  {clipCountLabel(collection.clip_count)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-muted-foreground">
          No collections yet. Make one here, or add clips from a project or the
          Media library.
        </p>
      )}
    </div>
  );
}
