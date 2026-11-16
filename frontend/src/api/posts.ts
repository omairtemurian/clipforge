import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { apiFetch } from "./client";
import { applyCover } from "./thumbnails";
import type {
  BulkSchedule,
  Post,
  PostCreate,
  PostPatch,
  PostTarget,
} from "./types";

export const postsKey = ["posts"] as const;

/** The statuses of the posting history. */
export type HistoryStatus = "published" | "failed" | "skipped";

/** When the posts go out: right away, at a time (ISO) or in each account's
 * next free slots of the bulk rules. */
export type PostWhen =
  | { kind: "now" }
  | { kind: "at"; at: string }
  | { kind: "bulk"; body: BulkSchedule };

/** Draft the clip's posts on targets (POST /clips/{id}/posts). */
function createDrafts(
  clipId: number,
  targets: PostTarget[],
  scheduledAt: string | null,
  thumbnailAssetId: number | null,
): Promise<Post[]> {
  const body: PostCreate = {
    targets: targets as PostCreate["targets"],
    scheduled_at: scheduledAt,
    thumbnail_asset_id: thumbnailAssetId,
  };
  return apiFetch<Post[]>(`/clips/${clipId}/posts`, {
    method: "POST",
    json: body,
  });
}

/** Publish a post right away (POST /posts/{id}/publish). */
function publishNow(post: Post): Promise<Post> {
  return apiFetch<Post>(`/posts/${post.id}/publish`, { method: "POST" });
}

/** Queue a post at its own time (POST /posts/{id}/queue). */
function queue(post: Post): Promise<Post> {
  return apiFetch<Post>(`/posts/${post.id}/queue`, {
    method: "POST",
    json: {},
  });
}

/**
 * Post the clip to targets: drafts first (they keep the texts if a check
 * fails), then publish each now, or queue each at its time; the bulk
 * scheduler drafts and queues in one call, which saves nothing if a post
 * is refused. The cover goes on each draft; the bulk posts get it after,
 * as the cover of all the clip's draft and queued posts.
 */
export function useSchedulePosts(clipId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      targets,
      when,
      thumbnailAssetId,
    }: {
      targets: PostTarget[];
      when: PostWhen;
      thumbnailAssetId: number | null;
    }): Promise<Post[]> => {
      if (when.kind === "bulk") {
        const posts = await apiFetch<Post[]>("/posts/bulk-schedule", {
          method: "POST",
          json: when.body,
        });
        if (thumbnailAssetId !== null) {
          await applyCover(clipId, thumbnailAssetId);
        }
        return posts;
      }
      const drafts = await createDrafts(
        clipId,
        targets,
        when.kind === "at" ? when.at : null,
        thumbnailAssetId,
      );
      const send = when.kind === "now" ? publishNow : queue;
      return Promise.all(drafts.map(send));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: postsKey }),
  });
}

/** Every post, oldest first (GET /posts): the calendar's posts. */
export function usePosts() {
  return useQuery({
    queryKey: postsKey,
    queryFn: () => apiFetch<Post[]>("/posts"),
  });
}

/** The posting history (GET /posts/history): published, failed and skipped
 * posts (or those in status), newest first, at most limit. */
export function usePostHistory(status: HistoryStatus | "all", limit: number) {
  return useQuery({
    queryKey: [...postsKey, "history", status, limit],
    queryFn: () => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (status !== "all") params.set("status", status);
      return apiFetch<Post[]>(`/posts/history?${params}`);
    },
    placeholderData: keepPreviousData,
  });
}

/** A mutation of one post that refreshes the posts when it settles. */
function usePostMutation<T>(send: (input: T) => Promise<Post>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSettled: () => queryClient.invalidateQueries({ queryKey: postsKey }),
  });
}

/** Change a draft or queued post's text or time (PATCH /posts/{id});
 * fields left out of patch keep their value. */
export function useUpdatePost() {
  return usePostMutation(
    ({ id, patch }: { id: number; patch: Partial<PostPatch> }) =>
      apiFetch<Post>(`/posts/${id}`, { method: "PATCH", json: patch }),
  );
}

/** Cancel a draft or queued post (POST /posts/{id}/cancel). */
export function useCancelPost() {
  return usePostMutation((id: number) =>
    apiFetch<Post>(`/posts/${id}/cancel`, { method: "POST" }),
  );
}

/** Publish a post now, e.g. a skipped or failed one again
 * (POST /posts/{id}/publish). */
export function usePublishPost() {
  return usePostMutation(publishNow);
}

/** Queue a draft at its own time (POST /posts/{id}/queue). */
export function useQueuePost() {
  return usePostMutation((post: Post) => queue(post));
}

/** Post every clip to every target in the accounts' next free slots
 * (POST /posts/bulk-schedule). */
export function useBulkSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BulkSchedule) =>
      apiFetch<Post[]>("/posts/bulk-schedule", { method: "POST", json: body }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: postsKey }),
  });
}
