import { useState } from "react";
import {
  ArrowSquareOutIcon,
  SlidersHorizontalIcon,
  TrashIcon,
} from "@phosphor-icons/react";
import {
  useChangeChannel,
  useChannelVideos,
  useRemoveChannel,
} from "@/api/autoImport";
import type { WatchedChannel } from "@/api/types";
import { ChannelDefaultsDialog } from "@/components/autoimport/ChannelDefaultsDialog";
import { ChannelVideos } from "@/components/autoimport/ChannelVideos";
import { Button } from "@/components/ui/button";
import { ToggleRow } from "@/components/ui/toggle-row";
import { ModeBadge } from "@/components/watch/ModeBadge";
import {
  channelName,
  channelUrl,
  importedVideos,
  lastCheckedLabel,
  newProjectsLabel,
} from "@/lib/autoImport";
import { GENRES } from "@/lib/processingSettings";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/**
 * One watched channel: its name, how it is watched (push or polling), when
 * its feed was last read (and the error
 * if the last read failed), the projects its new videos became, the saved
 * defaults, and the actions: pause or resume, edit defaults, remove.
 */
export function ChannelCard({ channel }: { channel: WatchedChannel }) {
  const videos = useChannelVideos(channel.id, true);
  const change = useChangeChannel();
  const remove = useRemoveChannel();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const name = channelName(channel);
  const genre = GENRES.find((g) => g.value === channel.settings.genre)?.label;

  return (
    <li
      aria-label={name}
      className={cn(cardClass(), "flex flex-col gap-4 p-5")}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-section">{name}</h3>
            <ModeBadge state={channel.push_state} />
          </div>
          <p className="mt-1 text-body text-muted-foreground">
            {lastCheckedLabel(channel.last_checked_at)}
            {" · "}
            {newProjectsLabel(importedVideos(videos.data ?? []).length)}
          </p>
          <p className="mt-1 text-caption text-muted-foreground">
            {genre} · {channel.settings.num_clips} clips ·{" "}
            {channel.settings.aspect}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Open ${name} on YouTube`}
            asChild
          >
            <a href={channelUrl(channel)} target="_blank" rel="noreferrer">
              <ArrowSquareOutIcon aria-hidden />
            </a>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing(true)}
            aria-label={`Edit defaults of ${name}`}
          >
            <SlidersHorizontalIcon aria-hidden />
            Edit defaults
          </Button>
          {confirming ? (
            <>
              <Button
                variant="destructive"
                size="sm"
                disabled={remove.isPending}
                onClick={() => remove.mutate(channel.id)}
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
      {channel.last_error && (
        <p role="alert" className="text-body text-destructive">
          Could not read the channel&apos;s feed: {channel.last_error}
        </p>
      )}
      {channel.push_error && (
        <p className="text-caption text-muted-foreground">
          Push is off ({channel.push_error}); the feed is polled instead.
        </p>
      )}
      <ToggleRow
        label="Import new videos"
        hint="Off pauses this channel; nothing is imported until you turn it on."
        checked={channel.enabled}
        disabled={change.isPending}
        onCheckedChange={(enabled) =>
          change.mutate({ id: channel.id, patch: { enabled } })
        }
      />
      {videos.isError ? (
        <p role="alert" className="text-body text-destructive">
          Could not load the videos.
        </p>
      ) : (
        videos.data && <ChannelVideos videos={videos.data} />
      )}
      {editing && (
        <ChannelDefaultsDialog
          channel={channel}
          onClose={() => setEditing(false)}
        />
      )}
    </li>
  );
}
