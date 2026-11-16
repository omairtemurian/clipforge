import { apiFetch } from "./client";
import type { PostCopy, PostCopyRequest } from "./types";

/** The options of "Rewrite with AI"; each one changes its own fields. */
export type RewriteOptions = Partial<
  Pick<PostCopyRequest, "tone" | "format" | "hashtags">
>;

/**
 * Write the clip's post for a platform (POST /clips/{id}/post-copy):
 * nothing is saved, the answer is for the modal's form. The automatic copy
 * on opening is `silent` (the modal shows one quiet notice instead of a
 * toast per platform). `accountId` is the account the post is for: the API
 * adds its always-included hashtags (the global and the campaign's are
 * always added).
 */
export function fetchPostCopy(
  clipId: number,
  platform: PostCopyRequest["platform"],
  options: RewriteOptions & {
    current?: PostCopy;
    silent?: boolean;
    accountId?: number | null;
  } = {},
): Promise<PostCopy> {
  const { tone, format, hashtags, current, silent, accountId } = options;
  const request: PostCopyRequest = {
    platform,
    tone: tone ?? null,
    format: format ?? null,
    hashtags: hashtags ?? null,
    current: current ?? null,
    account_id: accountId ?? null,
  };
  return apiFetch<PostCopy>(`/clips/${clipId}/post-copy`, {
    method: "POST",
    json: request,
    silent,
  });
}
