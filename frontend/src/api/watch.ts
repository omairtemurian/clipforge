import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  WatchEvent,
  WatchStatus,
  WatchedStreamer,
  WatchedStreamerCreate,
  WatchedStreamerPatch,
} from "./types";
import { toast } from "@/lib/toast";

export const watchEventsKey = ["watch", "events"] as const;
const streamersKey = ["watch", "streamers"] as const;
const POLL_MS = 15000;
const RECENT_ALERTS = 20;

/** What the creator watch can do here (GET /watch/status): push or
 * polling, the poll interval, Twitch keys, @handle lookups. */
export function useWatchStatus() {
  return useQuery({
    queryKey: ["watch", "status"],
    queryFn: () => apiFetch<WatchStatus>("/watch/status"),
    staleTime: 60_000,
  });
}

/** The latest alerts (new uploads and go-lives), newest first. */
export function useWatchEvents() {
  return useQuery({
    queryKey: watchEventsKey,
    queryFn: () =>
      apiFetch<WatchEvent[]>(`/watch/events?limit=${RECENT_ALERTS}`),
    refetchInterval: POLL_MS,
  });
}

/** The alerts after the one with id `after`, newest first; failures are
 * not toasted (the global alert poll retries on its own). */
export function fetchEventsAfter(after: number): Promise<WatchEvent[]> {
  return apiFetch<WatchEvent[]>(`/watch/events?after=${after}`, {
    silent: true,
  });
}

/** The watched Twitch streamers, refreshed to follow go-lives. */
export function useStreamers() {
  return useQuery({
    queryKey: streamersKey,
    queryFn: () => apiFetch<WatchedStreamer[]>("/watch/streamers"),
    refetchInterval: POLL_MS,
  });
}

/** Watch a Twitch streamer (POST /watch/streamers). */
export function useAddStreamer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: WatchedStreamerCreate) =>
      apiFetch<WatchedStreamer>("/watch/streamers", {
        method: "POST",
        json: body,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: streamersKey });
      toast.success(
        "Watching the streamer. You get an alert when they go live.",
      );
    },
  });
}

/** Switch a streamer's alerts on or off (PATCH). */
export function useChangeStreamer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: WatchedStreamerPatch }) =>
      apiFetch<WatchedStreamer>(`/watch/streamers/${id}`, {
        method: "PATCH",
        json: patch,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: streamersKey }),
  });
}

/** Stop watching a streamer (DELETE); past alerts stay. */
export function useRemoveStreamer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/watch/streamers/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: streamersKey }),
  });
}
