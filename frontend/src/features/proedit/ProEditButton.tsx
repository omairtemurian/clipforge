import { MagicWandIcon } from "@phosphor-icons/react";
import { useState, type MouseEvent } from "react";
import type { Clip } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useProEditEnabled } from "./api";
import { ProEditDialog } from "./ProEditDialog";

interface ProEditButtonProps {
  clip: Clip;
  /** "icon": the small square action of a gallery card. */
  look?: "outline" | "icon";
  /** The class of the icon look (the card's action style). */
  className?: string;
}

/** The "Pro Edit" button of an original clip: it opens the Pro Edit
 * dialog. Shown only while Pro Edit is enabled on the server, never on a
 * variant. */
export function ProEditButton({
  clip,
  look = "outline",
  className,
}: ProEditButtonProps) {
  const { enabled } = useProEditEnabled();
  const [open, setOpen] = useState(false);
  if (!enabled || clip.variant !== "original") return null;

  const openDialog = (event: MouseEvent) => {
    event.stopPropagation();
    setOpen(true);
  };
  return (
    <>
      {look === "icon" ? (
        <button
          type="button"
          aria-label="Pro Edit"
          title="Pro Edit: make a heavy-edit variant"
          onClick={openDialog}
          className={className}
        >
          <MagicWandIcon className="size-4" aria-hidden />
        </button>
      ) : (
        <Button
          type="button"
          variant="outline"
          title="Make a heavy-edit variant of this clip"
          onClick={openDialog}
          className={className}
        >
          <MagicWandIcon aria-hidden />
          Pro Edit
        </Button>
      )}
      {open && <ProEditDialog clip={clip} onClose={() => setOpen(false)} />}
    </>
  );
}
