import { useState, type FormEvent } from "react";
import { useRenameCollection } from "@/api/collections";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";
import { COLLECTION_NAME_MAX } from "@/lib/library";

interface RenameCollectionDialogProps {
  id: number;
  name: string;
  onClose: () => void;
}

/** A dialog that gives a collection a new (not blank) name. */
export function RenameCollectionDialog({
  id,
  name: current,
  onClose,
}: RenameCollectionDialogProps) {
  const [name, setName] = useState(current);
  const rename = useRenameCollection();
  const trimmed = name.trim();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!trimmed) return;
    rename.mutate({ id, name: trimmed }, { onSuccess: onClose });
  }

  return (
    <DialogFrame
      title="Rename collection"
      description="The name shown in the list and in the zip's manifest."
      onClose={onClose}
    >
      <form onSubmit={submit} className="mt-4">
        <label className="block text-body font-medium">
          Name
          <input
            value={name}
            maxLength={COLLECTION_NAME_MAX}
            onChange={(event) => setName(event.target.value)}
            className={`${INPUT} mt-1.5 h-9`}
          />
        </label>
        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!trimmed || rename.isPending}>
            Save
          </Button>
        </div>
      </form>
    </DialogFrame>
  );
}
