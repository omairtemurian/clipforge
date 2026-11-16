import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { ApiError } from "@/api/client";
import {
  DRIVE_SETUP_URL,
  driveKey,
  useConnectDrive,
  useDisconnectDrive,
  useDriveFile,
  useDriveStatus,
} from "@/api/gdrive";
import type { DriveFile } from "@/api/types";
import { Button } from "@/components/ui/button";

interface DriveImportDialogProps {
  onChoose: (file: DriveFile) => void;
  onClose: () => void;
}

/**
 * Import a video from Google Drive: explains the missing credentials, or
 * connects the account, or reads a pasted Drive link and hands the video to
 * onChoose (which opens the settings panel).
 */
export function DriveImportDialog({
  onChoose,
  onClose,
}: DriveImportDialogProps) {
  const status = useDriveStatus();

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-6 shadow-popover">
          <Dialog.Title className="text-lg font-semibold">
            Import from Google Drive
          </Dialog.Title>
          {status.isPending && (
            <Dialog.Description className="mt-1 text-sm text-muted-foreground">
              Checking Google Drive…
            </Dialog.Description>
          )}
          {status.isError && (
            <Dialog.Description className="mt-1 text-sm text-destructive">
              Could not check Google Drive: {status.error.message}
            </Dialog.Description>
          )}
          {status.data && !status.data.configured && <NeedsCredentials />}
          {status.data?.configured && !status.data.connected && <Connect />}
          {status.data?.connected && <PickFile onChoose={onChoose} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function NeedsCredentials() {
  return (
    <>
      <Dialog.Description asChild>
        <div className="mt-1 space-y-2 text-sm text-muted-foreground">
          <p role="status" className="font-medium text-foreground">
            Google Drive needs credentials
          </p>
          <p>
            Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in
            .env.local and restart ClipForge.{" "}
            <a
              href={DRIVE_SETUP_URL}
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2 hover:text-foreground"
            >
              See setup
            </a>
          </p>
        </div>
      </Dialog.Description>
      <CloseRow />
    </>
  );
}

function Connect() {
  const connect = useConnectDrive();
  return (
    <>
      <Dialog.Description className="mt-1 text-sm text-muted-foreground">
        {connect.isSuccess
          ? "Finish in the Google window that opened; this dialog continues by itself."
          : "Connect your Google account to import videos from your Drive. ClipForge only reads the files you import."}
      </Dialog.Description>
      <div className="mt-6 flex justify-end gap-2">
        <Dialog.Close asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </Dialog.Close>
        <Button
          type="button"
          disabled={connect.isPending}
          onClick={() => connect.mutate()}
        >
          {connect.isSuccess ? "Open Google again" : "Connect Google Drive"}
        </Button>
      </div>
    </>
  );
}

function PickFile({ onChoose }: { onChoose: (file: DriveFile) => void }) {
  const [link, setLink] = useState("");
  const lookup = useDriveFile();
  const disconnect = useDisconnectDrive();
  const queryClient = useQueryClient();
  const trimmed = link.trim();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!trimmed) return;
    lookup.mutate(trimmed, {
      onSuccess: onChoose,
      onError: (error) => {
        if (error instanceof ApiError && error.code === "drive_not_connected") {
          void queryClient.invalidateQueries({ queryKey: driveKey });
        }
      },
    });
  }

  return (
    <form onSubmit={submit} className="mt-1">
      <Dialog.Description className="text-sm text-muted-foreground">
        Paste the link of a video in your Drive (Share → Copy link).
      </Dialog.Description>
      <label htmlFor="drive-link" className="mt-4 block text-sm font-medium">
        Drive link
      </label>
      <input
        id="drive-link"
        value={link}
        onChange={(event) => setLink(event.target.value)}
        placeholder="https://drive.google.com/file/d/…"
        aria-invalid={lookup.isError}
        aria-describedby={lookup.isError ? "drive-error" : undefined}
        className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      {lookup.isError && (
        <p
          id="drive-error"
          role="alert"
          className="mt-2 text-sm text-destructive"
        >
          {lookup.error.message}
        </p>
      )}
      <div className="mt-6 flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          disabled={disconnect.isPending}
          onClick={() => disconnect.mutate()}
        >
          Disconnect
        </Button>
        <span className="flex-1" />
        <Dialog.Close asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </Dialog.Close>
        <Button type="submit" disabled={!trimmed || lookup.isPending}>
          Continue
        </Button>
      </div>
    </form>
  );
}

function CloseRow() {
  return (
    <div className="mt-6 flex justify-end">
      <Dialog.Close asChild>
        <Button type="button" variant="outline">
          Close
        </Button>
      </Dialog.Close>
    </div>
  );
}
