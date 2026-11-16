import { useState, type FormEvent } from "react";
import { FloppyDiskIcon, XIcon } from "@phosphor-icons/react";
import { Dialog } from "radix-ui";
import { useChangeChannel } from "@/api/autoImport";
import type { ProcessingSettings, WatchedChannel } from "@/api/types";
import { SourceRightsField } from "@/components/SourceRightsField";
import { SettingsFields } from "@/components/settings/SettingsFields";
import { Button } from "@/components/ui/button";
import { ToggleRow } from "@/components/ui/toggle-row";
import { channelName } from "@/lib/autoImport";
import { settingsToSend } from "@/lib/processingSettings";
import type { SourceRights } from "@/lib/sourceRights";

/**
 * The defaults of a channel's new projects: every processing setting, the
 * source rights, the credit line and whether the clips are scheduled as
 * drafts. They apply to the videos imported from the next poll on.
 */
export function ChannelDefaultsDialog({
  channel,
  onClose,
}: {
  channel: WatchedChannel;
  onClose: () => void;
}) {
  const change = useChangeChannel();
  const [settings, setSettings] = useState<ProcessingSettings>(
    channel.settings,
  );
  const [rights, setRights] = useState<SourceRights | "">(
    channel.source_rights ?? "",
  );
  const [creditLine, setCreditLine] = useState(channel.credit_line);
  const [drafts, setDrafts] = useState(channel.auto_schedule_drafts);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!rights || change.isPending) return;
    change.mutate(
      {
        id: channel.id,
        patch: {
          settings: settingsToSend(settings),
          source_rights: rights,
          credit_line: creditLine.trim(),
          auto_schedule_drafts: drafts,
        },
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed top-1/2 left-1/2 z-50 flex max-h-[90vh] w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-border bg-card shadow-popover outline-none"
        >
          <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
            <div className="flex shrink-0 items-center justify-between px-6 pt-5 pb-4">
              <Dialog.Title className="text-section">
                Defaults for {channelName(channel)}
              </Dialog.Title>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Close defaults"
                onClick={onClose}
              >
                <XIcon aria-hidden />
              </Button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-6 pb-4">
              <SettingsFields
                settings={settings}
                duration={null}
                allowSubtitles={false}
                onChange={(patch) => setSettings({ ...settings, ...patch })}
              />
              <SourceRightsField
                rights={rights}
                creditLine={creditLine}
                onRightsChange={setRights}
                onCreditLineChange={setCreditLine}
              />
              <ToggleRow
                label="Schedule clips as drafts"
                hint="Saved for when the scheduler is set up."
                checked={drafts}
                onCheckedChange={setDrafts}
              />
            </div>
            <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border px-6 py-4">
              <Button type="button" variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={!rights || change.isPending}>
                <FloppyDiskIcon aria-hidden />
                Save defaults
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
