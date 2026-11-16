import { Dialog } from "radix-ui";
import { XIcon } from "@phosphor-icons/react";
import type { PlatformStatus } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  platformLabel,
  signInLabel,
  type SocialPlatform,
} from "@/lib/platforms";
import { NeedsKeys } from "./NeedsKeys";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

interface ConnectionsDialogProps {
  platforms: PlatformStatus[];
  /** The platform whose sign-in window is open, if any. */
  waitingFor: SocialPlatform | null;
  connecting: boolean;
  onConnect: (platform: SocialPlatform) => void;
  onClose: () => void;
}

/** The "Social account connections" modal: a tile per platform with its
 * sign-in button, or what its developer app still needs. */
export function ConnectionsDialog({
  platforms,
  waitingFor,
  connecting,
  onConnect,
  onClose,
}: ConnectionsDialogProps) {
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-6 shadow-popover">
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-section">
              Social account connections
            </Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Close">
                <XIcon aria-hidden />
              </Button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="mt-1 text-body text-muted-foreground">
            {waitingFor
              ? `Finish in the ${platformLabel(waitingFor)} window that opened; this list updates by itself.`
              : "Pick a platform to sign in with. You can connect several accounts of one platform."}
          </Dialog.Description>
          <ul className="mt-5 grid gap-3 sm:grid-cols-2">
            {platforms.map((status) => (
              <li
                key={status.platform}
                aria-label={platformLabel(status.platform)}
                className={cn(
                  cardClass(),
                  "flex flex-col gap-3 p-4 bg-background",
                )}
              >
                <p className="font-medium">{platformLabel(status.platform)}</p>
                {status.configured ? (
                  <Button
                    size="sm"
                    disabled={connecting}
                    onClick={() => onConnect(status.platform)}
                  >
                    {waitingFor === status.platform
                      ? "Open sign-in again"
                      : signInLabel(status.platform)}
                  </Button>
                ) : (
                  <NeedsKeys status={status} />
                )}
              </li>
            ))}
          </ul>
          <div className="mt-6 flex justify-end">
            <Dialog.Close asChild>
              <Button type="button" variant="outline">
                Close
              </Button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
