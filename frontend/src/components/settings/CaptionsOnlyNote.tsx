import { WarningIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { formatDuration } from "@/lib/format";

/** Captions only on more than this many seconds of video is likely a mistake. */
export const LONG_CAPTIONS_ONLY_S = 180;

interface CaptionsOnlyNoteProps {
  /** Seconds of video that would become the one clip (null: unknown yet). */
  length: number | null;
  onUseAi: () => void;
}

/**
 * What the Captions only mode does (no clipping: the whole video, or the
 * timeframe, as one clip), with a warning and a way back to AI clipping
 * when that one clip would be longer than LONG_CAPTIONS_ONLY_S.
 */
export function CaptionsOnlyNote({ length, onUseAi }: CaptionsOnlyNoteProps) {
  const long = length !== null && length > LONG_CAPTIONS_ONLY_S;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-body text-muted-foreground">
        No clipping: the whole video, or the timeframe below, becomes one clip
        with captions, reframing and the edits you turn on. No AI picks moments.
      </p>
      {long && (
        <div
          role="note"
          aria-label="Long captions-only clip"
          className="flex flex-col items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-caption text-foreground"
        >
          <p className="flex gap-1.5">
            <WarningIcon
              className="mt-0.5 size-4 shrink-0 text-warning"
              aria-hidden
            />
            <span>
              This makes one {formatDuration(length)} clip, not shorts. Are you
              sure? To get short clips, use AI clipping, or set a shorter
              timeframe below.
            </span>
          </p>
          <Button type="button" variant="outline" size="xs" onClick={onUseAi}>
            Switch to AI clipping
          </Button>
        </div>
      )}
    </div>
  );
}
