import { useState } from "react";
import { FolderPlusIcon } from "@phosphor-icons/react";
import { AddToCollectionDialog } from "@/components/library/AddToCollectionDialog";
import { Button } from "@/components/ui/button";
import { clipCountLabel } from "@/lib/format";

interface AddClipsToCollectionProps {
  clipIds: number[];
  /** The name a new collection starts with. */
  suggestedName: string;
}

/** An "Add to collection" button for the clips shown, with its dialog. */
export function AddClipsToCollection({
  clipIds,
  suggestedName,
}: AddClipsToCollectionProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="outline"
        disabled={clipIds.length === 0}
        onClick={() => setOpen(true)}
      >
        <FolderPlusIcon aria-hidden />
        Add to collection
      </Button>
      {open && (
        <AddToCollectionDialog
          what={clipCountLabel(clipIds.length)}
          suggestedName={suggestedName}
          clipIds={() => Promise.resolve(clipIds)}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
