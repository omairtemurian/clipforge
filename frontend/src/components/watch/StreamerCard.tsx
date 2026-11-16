import { useState } from "react";
import { ArrowSquareOutIcon, TrashIcon } from "@phosphor-icons/react";
import { useChangeStreamer, useRemoveStreamer } from "@/api/watch";
import type { WatchedStreamer } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ToggleRow } from "@/components/ui/toggle-row";
import { ModeBadge } from "@/components/watch/ModeBadge";
import { lastCheckedLabel } from "@/lib/autoImport";
import { formatDate } from "@/lib/format";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** "Live now", "Last live <date>" or "Not seen live yet". */
function liveLabel(streamer: WatchedStreamer): string {
  if (streamer.live_since) return "Live now";
  if (streamer.last_live_at)
    return `Last live ${formatDate(streamer.last_live_at)}`;
  return "Not seen live yet";
}

/**
 * One watched Twitch streamer: live or not, how it is watched (push or
 * polling), when it was last checked and its error; switch its alerts off
 * or remove it.
 */
export function StreamerCard({ streamer }: { streamer: WatchedStreamer }) {
  const change = useChangeStreamer();
  const remove = useRemoveStreamer();
  const [confirming, setConfirming] = useState(false);
  const name = streamer.display_name || streamer.login;

  return (
    <li
      aria-label={name}
      className={cn(cardClass(), "flex flex-col gap-4 p-5")}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-section">{name}</h3>
            <ModeBadge state={streamer.push_state} />
          </div>
          <p className="mt-1 text-body text-muted-foreground">
            <span
              className={
                streamer.live_since ? "font-medium text-destructive" : ""
              }
            >
              {liveLabel(streamer)}
            </span>
            {" · "}
            {lastCheckedLabel(streamer.last_checked_at)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Open ${name} on Twitch`}
            asChild
          >
            <a
              href={`https://www.twitch.tv/${streamer.login}`}
              target="_blank"
              rel="noreferrer"
            >
              <ArrowSquareOutIcon aria-hidden />
            </a>
          </Button>
          {confirming ? (
            <>
              <Button
                variant="destructive"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(streamer.id)}
              >
                Remove {name}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirming(false)}
              >
                Keep
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`Remove ${name}`}
              onClick={() => setConfirming(true)}
            >
              <TrashIcon aria-hidden />
            </Button>
          )}
        </div>
      </div>
      {streamer.last_error && (
        <p role="alert" className="text-body text-destructive">
          Could not check the streamer: {streamer.last_error}
        </p>
      )}
      <ToggleRow
        label="Alert when live"
        hint="Off pauses this streamer; no go-live alert until you turn it on."
        checked={streamer.enabled}
        disabled={change.isPending}
        onCheckedChange={(enabled) =>
          change.mutate({ id: streamer.id, patch: { enabled } })
        }
      />
    </li>
  );
}
