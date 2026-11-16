import type { ReactNode } from "react";
import { AlertDialog } from "radix-ui";
import { buttonVariants } from "@/components/ui/button";

interface ConfirmDialogProps {
  title: string;
  children: ReactNode;
  /** The label of the button that does it ("Delete", "Archive"). */
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  /** A red confirm button, for what cannot be undone. */
  destructive?: boolean;
}

/** A modal that asks before an action, open while mounted. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onClose,
  destructive = false,
}: ConfirmDialogProps) {
  return (
    <AlertDialog.Root open onOpenChange={(open) => !open && onClose()}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-6 shadow-popover">
          <AlertDialog.Title className="text-lg font-semibold">
            {title}
          </AlertDialog.Title>
          <AlertDialog.Description className="mt-2 text-sm text-muted-foreground">
            {children}
          </AlertDialog.Description>
          <div className="mt-6 flex justify-end gap-2">
            <AlertDialog.Cancel
              className={buttonVariants({ variant: "outline" })}
            >
              Cancel
            </AlertDialog.Cancel>
            <AlertDialog.Action
              className={buttonVariants({
                variant: destructive ? "destructive" : "default",
              })}
              onClick={onConfirm}
            >
              {confirmLabel}
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
