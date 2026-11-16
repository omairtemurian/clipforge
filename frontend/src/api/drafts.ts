import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { postsKey } from "./posts";
import type { Draft, DraftApproval } from "./types";

export const draftsKey = ["drafts"] as const;

export type DraftStatus = Draft["status"];
export type RejectReason = NonNullable<Draft["reject_reason"]>;

/** The query string of GET /drafts for a status and campaign (null: all). */
function draftsQuery(status: DraftStatus, campaignId: number | null): string {
  const params = new URLSearchParams({ status });
  if (campaignId !== null) params.set("campaign_id", String(campaignId));
  return `/drafts?${params.toString()}`;
}

/** The drafts of the Approval Inbox with a status, newest first (of one
 * campaign, or of all when campaignId is null). */
export function useDrafts(status: DraftStatus, campaignId: number | null) {
  return useQuery({
    queryKey: [...draftsKey, status, campaignId],
    queryFn: () => apiFetch<Draft[]>(draftsQuery(status, campaignId)),
  });
}

/** After a decision: the inbox lists and the scheduled posts changed. */
function useRefreshAfterDecision() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: draftsKey }),
      queryClient.invalidateQueries({ queryKey: postsKey }),
    ]);
}

/** Approve a draft (owner only): its clip's posts are queued into the next
 * free posting slots of the campaign's autopilot. */
export function useApproveDraft() {
  const refresh = useRefreshAfterDecision();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<DraftApproval>(`/drafts/${id}/approve`, {
        method: "POST",
        json: {},
      }),
    onSettled: refresh,
  });
}

/** Reject a draft (owner only), with the reason if one was picked. */
export function useRejectDraft() {
  const refresh = useRefreshAfterDecision();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: RejectReason | null }) =>
      apiFetch<Draft>(`/drafts/${id}/reject`, {
        method: "POST",
        json: { reason },
      }),
    onSettled: refresh,
  });
}

/** Approve every pending draft of a campaign (owner only, after the
 * confirm dialog). */
export function useApproveCampaignDrafts() {
  const refresh = useRefreshAfterDecision();
  return useMutation({
    mutationFn: (campaignId: number) =>
      apiFetch<DraftApproval[]>(`/campaigns/${campaignId}/drafts/approve`, {
        method: "POST",
        json: {},
      }),
    onSettled: refresh,
  });
}
