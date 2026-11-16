import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { postsKey } from "./posts";
import type { Post, PostText, QuickPost } from "./types";
import type { PostPlatform } from "@/lib/postForm";

/** Who a quick post goes to: each platform's default account, or the
 * chosen accounts. */
export type QuickTargets =
  | { kind: "defaults"; platforms: PostPlatform[] }
  | { kind: "accounts"; accountIds: number[] };

/**
 * Post the clip in one call (POST /clips/{id}/quick-post): the API renders
 * it if needed, queues a post per target with the texts of the sheet and
 * uploads them right after. Only the owner's click may do this.
 */
export function useQuickPost(clipId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      targets,
      texts,
    }: {
      targets: QuickTargets;
      texts: Partial<Record<PostPlatform, PostText>>;
    }): Promise<Post[]> => {
      const body: QuickPost = {
        texts,
        ...(targets.kind === "defaults"
          ? { platforms: targets.platforms }
          : { account_ids: targets.accountIds }),
      };
      return apiFetch<Post[]>(`/clips/${clipId}/quick-post`, {
        method: "POST",
        json: body,
      });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: postsKey }),
  });
}
