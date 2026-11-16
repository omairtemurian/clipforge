import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/api/client";
import { draftsKey } from "@/api/drafts";
import { postsKey } from "@/api/posts";
import type { Draft, DraftApproval } from "@/api/types";
import { toast } from "@/lib/toast";

const WAITING: Draft["status"][] = ["pending", "needs_fix"];

/** The draft of clip clipId in campaign campaignId: its existing one
 * (GET /drafts), else a new one (POST /drafts). */
async function draftOf(clipId: number, campaignId: number): Promise<Draft> {
  const drafts = await apiFetch<Draft[]>(`/drafts?campaign_id=${campaignId}`);
  const found = drafts.find((draft) => draft.clip_id === clipId);
  if (found) return found;
  return apiFetch<Draft>("/drafts", {
    method: "POST",
    json: { clip_id: clipId },
  });
}

/** Approve a Pro Edit variant: its draft (made now if it has none) is
 * approved, so its posts are queued like any approved clip's. A variant
 * whose draft was already decided is not approved again. */
async function approveVariant({
  variantId,
  campaignId,
}: {
  variantId: number;
  campaignId: number;
}): Promise<DraftApproval> {
  const draft = await draftOf(variantId, campaignId);
  if (!WAITING.includes(draft.status)) {
    throw new Error(`The Pro Edit's draft is already ${draft.status}.`);
  }
  return apiFetch<DraftApproval>(`/drafts/${draft.id}/approve`, {
    method: "POST",
    json: {},
  });
}

/** The mutation that approves a Pro Edit variant from the inbox. Errors of
 * the API are toasted by apiFetch, the others here. */
export function useApproveVariant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: approveVariant,
    onError: (error) => {
      if (!(error instanceof ApiError)) toast.error(error.message);
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: draftsKey }),
        queryClient.invalidateQueries({ queryKey: postsKey }),
      ]),
  });
}
