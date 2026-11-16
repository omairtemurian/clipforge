import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  WatchedChannel,
  WatchedChannelCreate,
  WatchedChannelPatch,
  WatchedVideo,
} from "./types";
import { toast } from "@/lib/toast";

export const watchedChannelsKey = ["auto-import", "channels"] as const;

const channelVideosKey = (channelId: number) =>
  ["auto-import", "videos", channelId] as const;

const POLL_MS = 15000;

/** The watched channels (GET /auto-import/channels), refreshed so that the
 * last checked time follows the importer's polls. */
export function useWatchedChannels() {
  return useQuery({
    queryKey: watchedChannelsKey,
    queryFn: () => apiFetch<WatchedChannel[]>("/auto-import/channels"),
    refetchInterval: POLL_MS,
  });
}

/** The videos seen in one channel's feed, newest first; fetched while
 * `enabled`. */
export function useChannelVideos(channelId: number, enabled: boolean) {
  return useQuery({
    queryKey: channelVideosKey(channelId),
    queryFn: () =>
      apiFetch<WatchedVideo[]>(`/auto-import/channels/${channelId}/videos`),
    enabled,
    refetchInterval: POLL_MS,
  });
}

/** Watch a channel (POST /auto-import/channels). */
export function useAddChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: WatchedChannelCreate) =>
      apiFetch<WatchedChannel>("/auto-import/channels", {
        method: "POST",
        json: body,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: watchedChannelsKey });
      toast.success("Watching the channel. New videos become projects.");
    },
  });
}

/** Change a channel's defaults or switch it on or off (PATCH). */
export function useChangeChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: WatchedChannelPatch }) =>
      apiFetch<WatchedChannel>(`/auto-import/channels/${id}`, {
        method: "PATCH",
        json: patch,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: watchedChannelsKey }),
  });
}

/** Stop watching a channel (DELETE); the projects made from it stay. */
export function useRemoveChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/auto-import/channels/${id}`, { method: "DELETE" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: watchedChannelsKey }),
  });
}
