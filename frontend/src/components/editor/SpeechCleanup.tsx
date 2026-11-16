import {
  CircleNotchIcon,
  PauseIcon,
  SparkleIcon,
  WaveformIcon,
  XIcon,
} from "@phosphor-icons/react";
import { Dialog } from "radix-ui";
import { useState } from "react";
import { useCleanupSuggestions } from "@/api/clips";
import type { CleanupSuggestion } from "@/api/types";
import { Button } from "@/components/ui/button";
import { cleanupCuts, isApplied, suggestionLabel } from "@/lib/cleanup";
import { formatTimecode } from "@/lib/format";
import type { ClipRange, CutRange } from "@/lib/timeline";
import { formatPause } from "@/lib/transcriptView";
import { Skeleton } from "@/components/ui/skeleton";

interface SpeechCleanupProps {
  clipId: number;
  /** The clip's span as edited now: the suggestions are for it. */
  range: ClipRange;
  cuts: CutRange[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Cut the checked suggestions from the clip (one undo step). */
  onApply: (cuts: CutRange[]) => void;
}

function SuggestionRow({
  suggestion,
  applied,
  checked,
  onToggle,
}: {
  suggestion: CleanupSuggestion;
  applied: boolean;
  checked: boolean;
  onToggle: () => void;
}) {
  const Icon = suggestion.kind === "filler" ? WaveformIcon : PauseIcon;
  return (
    <li>
      <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2 text-body transition-colors hover:bg-muted/60 has-disabled:cursor-default has-disabled:opacity-60">
        <input
          type="checkbox"
          checked={checked || applied}
          disabled={applied}
          onChange={onToggle}
          className="size-4 accent-primary"
        />
        <Icon className="size-4 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-medium">
          {suggestionLabel(suggestion)}
        </span>
        <span className="text-caption text-muted-foreground tabular-nums">
          {applied
            ? "Already removed"
            : `${formatTimecode(suggestion.start)} · ${formatPause(suggestion.end - suggestion.start)}`}
        </span>
      </label>
    </li>
  );
}

/** The review list of the open dialog; its checks reset on every open. */
function CleanupReview({
  clipId,
  range,
  cuts,
  onOpenChange,
  onApply,
}: Omit<SpeechCleanupProps, "open">) {
  const suggestions = useCleanupSuggestions(clipId, range, true);
  const [unchecked, setUnchecked] = useState<ReadonlySet<number>>(new Set());
  const list = suggestions.data ?? [];
  const chosen = cleanupCuts(list, unchecked, cuts);

  const toggle = (index: number) => {
    const next = new Set(unchecked);
    if (!next.delete(index)) next.add(index);
    setUnchecked(next);
  };
  const apply = () => {
    onApply(chosen);
    onOpenChange(false);
  };

  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-4">
        {suggestions.isPending && (
          <div aria-label="Loading suggestions" className="flex flex-col gap-2">
            {[0, 1, 2].map((row) => (
              <Skeleton key={row} className="h-10 rounded-lg" />
            ))}
          </div>
        )}
        {suggestions.isError && (
          <p role="alert" className="text-body text-muted-foreground">
            The suggestions could not be loaded.
          </p>
        )}
        {suggestions.isSuccess && list.length === 0 && (
          <p className="text-body text-muted-foreground">
            No filler words or long pauses were found in this clip.
          </p>
        )}
        {list.length > 0 && (
          <ul aria-label="Suggested cuts" className="flex flex-col gap-2">
            {list.map((suggestion, index) => (
              <SuggestionRow
                key={`${suggestion.start}-${suggestion.end}`}
                suggestion={suggestion}
                applied={isApplied(suggestion, cuts)}
                checked={!unchecked.has(index)}
                onToggle={() => toggle(index)}
              />
            ))}
          </ul>
        )}
      </div>
      <div className="flex shrink-0 items-center justify-end gap-2 rounded-b-2xl border-t border-border px-6 py-4">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button disabled={chosen.length === 0} onClick={apply}>
          {suggestions.isPending ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <SparkleIcon aria-hidden />
          )}
          {chosen.length === 1
            ? "Remove 1 cut"
            : `Remove ${chosen.length} cuts`}
        </Button>
      </div>
    </>
  );
}

/**
 * Speech cleanup: a dialog listing the filler words and long pauses that
 * polish finds in the clip's span, each with a checkbox (checked at
 * first). Applying cuts the checked ones; unchecked ones stay in the clip.
 */
export function SpeechCleanup({ open, ...review }: SpeechCleanupProps) {
  return (
    <Dialog.Root open={open} onOpenChange={review.onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 flex max-h-[80vh] w-[calc(100%-2rem)] max-w-[560px] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-border bg-card shadow-popover outline-none">
          <div className="flex shrink-0 items-start justify-between gap-4 px-6 pt-5 pb-4">
            <div>
              <Dialog.Title className="text-section">
                Speech cleanup
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-body text-muted-foreground">
                Filler words and long pauses in this clip. Uncheck the ones to
                keep, then remove the rest.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Close">
                <XIcon aria-hidden />
              </Button>
            </Dialog.Close>
          </div>
          {open && <CleanupReview {...review} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
