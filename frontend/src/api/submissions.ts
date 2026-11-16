import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { SubmissionPatch, SubmissionView } from "./types";

export const submissionsKey = ["submissions"] as const;

/** The submissions of a campaign's published posts (newest first), each with
 * its copy text. */
export function useSubmissions(campaignId: number) {
  return useQuery({
    queryKey: [...submissionsKey, campaignId],
    queryFn: () =>
      apiFetch<SubmissionView[]>(`/submissions?campaign_id=${campaignId}`),
  });
}

/** The published posts of all campaigns that are not submitted on their
 * campaign board yet (the "Ready to submit" list), newest first. */
export function useReadySubmissions() {
  return useQuery({
    queryKey: [...submissionsKey, "ready"],
    queryFn: () =>
      apiFetch<SubmissionView[]>("/submissions?status=not_submitted"),
  });
}

/** Change a submission (tick it, record the board's answer, views, payout,
 * notes). */
export function useUpdateSubmission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: number;
      patch: Partial<SubmissionPatch>;
    }) =>
      apiFetch<SubmissionView>(`/submissions/${id}`, {
        method: "PATCH",
        json: patch,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: submissionsKey }),
  });
}
