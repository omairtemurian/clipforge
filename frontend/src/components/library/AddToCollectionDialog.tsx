import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import {
  useAddToCollection,
  useCollections,
  useCreateCollection,
} from "@/api/collections";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";
import { NativeSelect } from "@/components/ui/native-select";
import { COLLECTION_NAME_MAX } from "@/lib/library";
import { toast } from "@/lib/toast";

const NEW = "new";

interface AddToCollectionDialogProps {
  /** What is added, for the description ("3 clips", "5 moments"). */
  what: string;
  /** The name a new collection starts with. */
  suggestedName: string;
  /** The clips to add; may make them first (search moments). */
  clipIds: () => Promise<number[]>;
  /** Their renders were queued, so the collection shows them as such. */
  rendersQueued?: boolean;
  onClose: () => void;
}

/**
 * Adds clips to an existing collection or to a new one named here, then
 * opens that collection, where its zip can be downloaded.
 */
export function AddToCollectionDialog({
  what,
  suggestedName,
  clipIds,
  rendersQueued = false,
  onClose,
}: AddToCollectionDialogProps) {
  const collections = useCollections();
  const create = useCreateCollection();
  const add = useAddToCollection();
  const navigate = useNavigate();
  const [target, setTarget] = useState(NEW);
  const [name, setName] = useState(suggestedName);
  const [busy, setBusy] = useState(false);
  const trimmed = name.trim();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (target === NEW && !trimmed) return;
    setBusy(true);
    try {
      const id =
        target === NEW
          ? (await create.mutateAsync(trimmed)).id
          : Number(target);
      const ids = await clipIds();
      await add.mutateAsync({ id, clipIds: ids });
      toast.success(`Added ${what} to the collection.`);
      onClose();
      navigate(`/collections?id=${id}`, {
        state: rendersQueued ? { queued: ids } : null,
      });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
    } finally {
      setBusy(false);
    }
  }

  return (
    <DialogFrame
      title="Add to collection"
      description={`Put ${what} in a collection to export them together.`}
      onClose={onClose}
    >
      <form onSubmit={(event) => void submit(event)} className="mt-4 space-y-4">
        <label className="block text-body font-medium">
          Collection
          <span className="mt-1.5 block" />
          <NativeSelect
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            block
          >
            <option value={NEW}>New collection…</option>
            {collections.data?.map((collection) => (
              <option key={collection.id} value={collection.id}>
                {collection.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        {target === NEW && (
          <label className="block text-body font-medium">
            Name
            <input
              value={name}
              maxLength={COLLECTION_NAME_MAX}
              onChange={(event) => setName(event.target.value)}
              className={`${INPUT} mt-1.5 h-9`}
            />
          </label>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || (target === NEW && !trimmed)}>
            {busy ? "Adding…" : "Add"}
          </Button>
        </div>
      </form>
    </DialogFrame>
  );
}
