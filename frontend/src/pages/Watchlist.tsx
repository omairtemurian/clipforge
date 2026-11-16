import { useWatchedChannels } from "@/api/autoImport";
import { AddChannelForm } from "@/components/autoimport/AddChannelForm";
import { ChannelCard } from "@/components/autoimport/ChannelCard";
import { PageHeader } from "@/components/PageHeader";
import { RecentAlerts } from "@/components/watch/RecentAlerts";
import { StreamerSection } from "@/components/watch/StreamerSection";
import { WatchStatusBanner } from "@/components/watch/WatchStatusBanner";
import { MonitorPlayIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** Watchlist: the YouTube channels whose new videos become projects at
 * once, the Twitch streamers whose go-lives raise an alert, and the latest
 * alerts. */
export function WatchlistPage() {
  const channels = useWatchedChannels();

  return (
    <>
      <PageHeader
        title="Watchlist"
        description="Watch creators: each new YouTube video becomes a top-priority project with its channel's defaults, and a Twitch go-live raises an alert."
      />
      <div className={cn(pageColumn(), "flex flex-col gap-8 pb-10")}>
        <WatchStatusBanner />
        <section
          aria-labelledby="watch-youtube"
          className="flex flex-col gap-4"
        >
          <h2 id="watch-youtube" className="text-section">
            YouTube channels
          </h2>
          <AddChannelForm />
          {channels.isError && (
            <p role="alert" className="text-body text-destructive">
              Could not load the watched channels.
            </p>
          )}
          {channels.isSuccess && channels.data.length === 0 && (
            <EmptyState
              icon={MonitorPlayIcon}
              title="No channels yet"
              className="py-8"
              action={
                <Button
                  variant="secondary"
                  onClick={() =>
                    document.getElementById("auto-import-channel")?.focus()
                  }
                >
                  Add a channel
                </Button>
              }
            >
              Add one above to start importing its new videos.
            </EmptyState>
          )}
          {channels.data && channels.data.length > 0 && (
            <ul aria-label="Watched channels" className="flex flex-col gap-4">
              {channels.data.map((channel) => (
                <ChannelCard key={channel.id} channel={channel} />
              ))}
            </ul>
          )}
        </section>
        <StreamerSection />
        <RecentAlerts />
      </div>
    </>
  );
}
