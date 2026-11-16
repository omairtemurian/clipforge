import { Dialog } from "radix-ui";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface DialogFrameProps {
  title: string;
  description: string;
  onClose: () => void;
  /** A wider card, for lists. */
  wide?: boolean;
  children: ReactNode;
}

/** A centered modal card with a title and a description, open while mounted.
 * The card scrolls when it is taller than the viewport; a child that is a
 * min-h-0 flex column can scroll its own body instead and keep a footer in
 * view (ProEditDialog). */
export function DialogFrame({
  title,
  description,
  onClose,
  wide = false,
  children,
}: DialogFrameProps) {
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content
          className={cn(
            "fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100%-2rem)] w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-popover",
            wide ? "max-w-2xl" : "max-w-md",
          )}
        >
          <Dialog.Title className="text-section">{title}</Dialog.Title>
          <Dialog.Description className="mt-1 text-body text-muted-foreground">
            {description}
          </Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
