import { ShieldCheckIcon, ShieldWarningIcon } from "@phosphor-icons/react";
import { RIGHTS_OPTIONS, type SourceRights } from "@/lib/sourceRights";
import { cn } from "@/lib/utils";

/**
 * The reminder under the video preview that only videos the owner made or
 * may reuse should be clipped; once "Source rights" is chosen it says which
 * reason was confirmed.
 */
export function CopyrightNotice({ rights }: { rights: SourceRights | "" }) {
  const confirmed = RIGHTS_OPTIONS.find((option) => option.value === rights);
  const Icon = confirmed ? ShieldCheckIcon : ShieldWarningIcon;
  return (
    <div
      role="note"
      aria-label="Copyright notice"
      className={cn(
        "flex gap-2 rounded-lg border p-3 text-caption",
        confirmed
          ? "border-border text-muted-foreground"
          : "border-warning/40 bg-warning/10 text-foreground",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="flex flex-col gap-1">
        <p>
          Only clip videos you made yourself or have the right to reuse. Posting
          someone else&apos;s work without permission can get your clips taken
          down.
        </p>
        <p className="font-medium">
          {confirmed
            ? `You confirmed: ${confirmed.label}.`
            : "Choose under Source rights why you may use this video."}
        </p>
      </div>
    </div>
  );
}
