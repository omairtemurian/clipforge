import { useState, type FormEvent } from "react";
import {
  CircleNotchIcon,
  FloppyDiskIcon,
  SparkleIcon,
  XIcon,
} from "@phosphor-icons/react";
import { Dialog } from "radix-ui";
import { useSaveDefault } from "@/api/presets";
import type { VideoSource } from "@/api/projects";
import { useProcessingDefaults } from "@/api/sources";
import type { ProcessingSettings } from "@/api/types";
import { Button } from "@/components/ui/button";
import { SourceRightsField } from "@/components/SourceRightsField";
import { CopyrightNotice } from "@/components/settings/CopyrightNotice";
import { SettingsFields } from "@/components/settings/SettingsFields";
import { SourcePreview } from "@/components/settings/SourcePreview";
import { UploadProgress } from "@/components/settings/UploadProgress";
import { settingsToSend } from "@/lib/processingSettings";
import type { RightsChoice, SourceRights } from "@/lib/sourceRights";
import { useSourceDetails } from "@/lib/useSourceDetails";
import { Skeleton } from "@/components/ui/skeleton";

interface SettingsPanelProps {
  source: VideoSource;
  /** True while the project is being created. */
  busy: boolean;
  /** The share of the video file uploaded (0 to 1); null when none is. */
  uploadProgress?: number | null;
  /** Settings chosen on Home (the clipping mode, subtitles) that win over the default's. */
  initial?: Partial<ProcessingSettings>;
  onSubmit: (settings: ProcessingSettings, rights: RightsChoice) => void;
  onClose: () => void;
}

/**
 * How to process the chosen video (SPEC 8.2): the video on the left, every
 * processing setting on the right and "Get clips", which hands the settings
 * and the required source rights to onSubmit. A modal at most 90vh tall: the
 * body scrolls, the footer stays. The settings start as the saved default
 * (or the server's), and "Save as default" stores the current ones.
 */
export function SettingsPanel({
  source,
  busy,
  uploadProgress = null,
  initial,
  onSubmit,
  onClose,
}: SettingsPanelProps) {
  const details = useSourceDetails(source);
  const defaults = useProcessingDefaults();
  const saveDefault = useSaveDefault();
  const [draft, setDraft] = useState<ProcessingSettings | null>(null);
  const settings =
    draft ?? (defaults.data ? { ...defaults.data, ...initial } : null);
  const [rights, setRights] = useState<SourceRights | "">("");
  const [creditLine, setCreditLine] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!settings || !rights || busy || details.error) return;
    onSubmit(settingsToSend(settings), {
      source_rights: rights,
      credit_line: creditLine.trim(),
    });
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed top-1/2 left-1/2 z-50 flex max-h-[90vh] w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-border bg-card shadow-popover outline-none"
        >
          <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
            <div className="flex shrink-0 items-center justify-between px-6 pt-5 pb-4">
              <Dialog.Title className="text-section">
                Clip settings
              </Dialog.Title>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Close settings"
                onClick={onClose}
              >
                <XIcon aria-hidden />
              </Button>
            </div>
            <div className="grid min-h-0 flex-1 gap-8 overflow-y-auto px-6 pb-4 md:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
              <div className="flex flex-col gap-4 self-start md:sticky md:top-0">
                <SourcePreview details={details} />
                <CopyrightNotice rights={rights} />
              </div>
              {settings ? (
                <div className="flex min-w-0 flex-col gap-5">
                  <SettingsFields
                    settings={settings}
                    duration={details.duration}
                    onChange={(patch) => setDraft({ ...settings, ...patch })}
                  />
                  <SourceRightsField
                    rights={rights}
                    creditLine={creditLine}
                    onRightsChange={setRights}
                    onCreditLineChange={setCreditLine}
                  />
                </div>
              ) : defaults.isError ? (
                <div className="flex flex-col items-start gap-3 text-body text-muted-foreground">
                  <p>Could not load the default settings.</p>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void defaults.refetch()}
                  >
                    Try again
                  </Button>
                </div>
              ) : (
                <div
                  data-testid="settings-skeleton"
                  className="flex flex-col gap-6"
                >
                  {[0, 1, 2, 3].map((row) => (
                    <Skeleton key={row} className="h-14 rounded-lg" />
                  ))}
                </div>
              )}
            </div>
            <div className="flex shrink-0 items-center justify-end gap-2 rounded-b-2xl border-t border-border bg-card px-6 py-4">
              <Button
                type="button"
                variant="outline"
                size="lg"
                className="mr-auto"
                disabled={!settings || saveDefault.isPending}
                onClick={() =>
                  settings && saveDefault.mutate(settingsToSend(settings))
                }
              >
                <FloppyDiskIcon aria-hidden />
                Save as default
              </Button>
              {uploadProgress !== null && (
                <UploadProgress fraction={uploadProgress} />
              )}
              <Button type="button" variant="ghost" size="lg" onClick={onClose}>
                Cancel
              </Button>
              <Button
                type="submit"
                size="lg"
                className="h-10 rounded-full px-6"
                disabled={!settings || busy || details.error !== null}
              >
                {busy ? (
                  <CircleNotchIcon className="animate-spin" aria-hidden />
                ) : (
                  <SparkleIcon aria-hidden />
                )}
                Get clips
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
