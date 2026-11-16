import { useState, type FormEvent } from "react";
import { BroadcastIcon, PlusIcon } from "@phosphor-icons/react";
import { useAddStreamer, useStreamers, useWatchStatus } from "@/api/watch";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { StreamerCard } from "@/components/watch/StreamerCard";
import { cn } from "@/lib/utils";
import { cardClass } from "@/lib/surfaces";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * The Twitch part of the Watchlist: add a streamer by login or
 * twitch.tv link, then one card per streamer. Without the Twitch app keys
 * the streamers are kept but not checked, and the section says so.
 */
export function StreamerSection() {
  const status = useWatchStatus();
  const streamers = useStreamers();
  const add = useAddStreamer();
  const [login, setLogin] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!login.trim() || add.isPending) return;
    add.mutate({ login: login.trim() }, { onSuccess: () => setLogin("") });
  }

  return (
    <section aria-labelledby="watch-twitch" className="flex flex-col gap-4">
      <h2 id="watch-twitch" className="text-section">
        Twitch streamers
      </h2>
      {status.data && !status.data.twitch_configured && (
        <p
          role="note"
          className="rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-body"
        >
          Needs Twitch app keys: set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET
          (see the README) to get go-live alerts.
        </p>
      )}
      <form
        onSubmit={submit}
        aria-label="Watch a streamer"
        className={cn(cardClass(), "flex items-end gap-3 p-5")}
      >
        <div className="min-w-0 flex-1">
          <Field label="Twitch streamer" htmlFor="watch-streamer">
            <input
              id="watch-streamer"
              type="text"
              value={login}
              onChange={(event) => setLogin(event.target.value)}
              placeholder="Login or twitch.tv/… link"
              className={cn(INPUT, "h-9")}
            />
          </Field>
        </div>
        <Button type="submit" disabled={!login.trim() || add.isPending}>
          <PlusIcon aria-hidden />
          Watch streamer
        </Button>
      </form>
      {streamers.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the streamers.
        </p>
      )}
      {streamers.isSuccess && streamers.data.length === 0 && (
        <EmptyState
          icon={BroadcastIcon}
          title="No streamers yet"
          className="py-8"
          action={
            <Button
              variant="secondary"
              onClick={() => document.getElementById("watch-streamer")?.focus()}
            >
              Add a streamer
            </Button>
          }
        >
          Add one to get an alert when they go live.
        </EmptyState>
      )}
      {streamers.data && streamers.data.length > 0 && (
        <ul aria-label="Watched streamers" className="flex flex-col gap-4">
          {streamers.data.map((streamer) => (
            <StreamerCard key={streamer.id} streamer={streamer} />
          ))}
        </ul>
      )}
    </section>
  );
}
