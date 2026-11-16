import { Dialog } from "radix-ui";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";
import { Pill } from "@/components/ui/pill";
import type { Undo } from "@/hooks/useUndo";
import { timeAgo } from "@/lib/format";
import { versionSummary } from "@/lib/versions";

interface VersionHistoryDialogProps {
  undo: Undo;
  /** Unsaved edits, which a restore would drop: restore waits for them. */
  dirty: boolean;
  /** A save or render is under way. */
  busy: boolean;
  onClose: () => void;
}

/**
 * The clip's saved versions, newest first: what each one did, when, the
 * current one marked; "Restore" gives the clip a version's state as a new
 * version (undoable) and closes the dialog.
 */
export function VersionHistoryDialog({
  undo,
  dirty,
  busy,
  onClose,
}: VersionHistoryDialogProps) {
  const history = undo.history;
  const versions = [...(history?.versions ?? [])].reverse();
  const blocked = dirty || busy || undo.moving;
  const restore = async (number: number) => {
    if (await undo.restore(number)) onClose();
  };

  return (
    <DialogFrame
      title="Version history"
      description="Every saved change of the clip. Restoring a version keeps the others."
      onClose={onClose}
      wide
    >
      {versions.length === 0 ? (
        <p className="mt-4 text-body text-muted-foreground">
          No saved versions yet.
        </p>
      ) : (
        <ol aria-label="Versions" className="mt-4 flex flex-col gap-2">
          {versions.map((version) => {
            const current = version.number === history?.current;
            return (
              <li
                key={version.number}
                aria-label={`Version ${version.number}`}
                className="flex items-center gap-3 rounded-lg border border-border px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 text-body font-medium">
                    Version {version.number}
                    {current && <Pill tone="primary">Current</Pill>}
                  </p>
                  <p className="truncate text-caption text-muted-foreground">
                    {versionSummary(version)} · {timeAgo(version.created_at)}
                  </p>
                </div>
                {!current && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={blocked}
                    title={dirty ? "Save the changes first" : undefined}
                    onClick={() => void restore(version.number)}
                  >
                    Restore
                  </Button>
                )}
              </li>
            );
          })}
        </ol>
      )}
      <div className="mt-6 flex justify-end">
        <Dialog.Close asChild>
          <Button type="button" variant="outline">
            Close
          </Button>
        </Dialog.Close>
      </div>
    </DialogFrame>
  );
}
