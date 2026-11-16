import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { projectsKey } from "@/api/projects";
import type {
  ProEditChoices,
  ProEditEstimate,
  ProEditOptions,
  ProEditRun,
  ProEditStarted,
  ProEditStatus,
} from "@/api/types";
import { proEditStatusKey } from "./api";
import { estimateQuery } from "./options";

/** GET /proedit/status: the flag and the critic's round cap (N of the
 * progress view's "critic round n/N"). */
export function useProEditStatus() {
  return useQuery({
    queryKey: proEditStatusKey,
    queryFn: () => apiFetch<ProEditStatus>("/proedit/status", { silent: true }),
    staleTime: Infinity,
  });
}

/** What the Pro Edit dialog offers for clip clipId
 * (GET /proedit/clips/{id}/choices). */
export function useProEditChoices(clipId: number) {
  return useQuery({
    queryKey: ["proedit", "choices", clipId],
    queryFn: () => apiFetch<ProEditChoices>(`/proedit/clips/${clipId}/choices`),
  });
}

/** The LLM cost estimate of a Pro Edit of clip clipId with options
 * (GET /proedit/clips/{id}/estimate); the last one stays while the next
 * loads. Failures are shown by the dialog, not as toasts. */
export function useProEditEstimate(clipId: number, options: ProEditOptions) {
  const query = estimateQuery(options);
  return useQuery({
    queryKey: ["proedit", "estimate", clipId, query],
    queryFn: () =>
      apiFetch<ProEditEstimate>(`/proedit/clips/${clipId}/estimate?${query}`, {
        silent: true,
      }),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

/** After a run was queued: the project's clips and jobs (the new variant,
 * its job), the clip's variants and the variant's runs changed (the editor
 * follows the run's job from its runs, ProEditEditor). */
function useRefreshAfterRun() {
  const queryClient = useQueryClient();
  return (started: ProEditStarted) =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: [...projectsKey, started.clip.project_id],
      }),
      queryClient.invalidateQueries({ queryKey: ["proedit", "variants"] }),
      queryClient.invalidateQueries({ queryKey: ["clips", started.clip.id] }),
      queryClient.invalidateQueries({
        queryKey: ["proedit", "runs", started.clip.id],
      }),
    ]);
}

/** Make a Pro Edit variant of clip clipId (POST /proedit/clips/{id}/runs). */
export function useStartProEdit(clipId: number) {
  const refresh = useRefreshAfterRun();
  return useMutation({
    mutationFn: (options: ProEditOptions) =>
      apiFetch<ProEditStarted>(`/proedit/clips/${clipId}/runs`, {
        method: "POST",
        json: options,
      }),
    onSuccess: refresh,
  });
}

/** Render variants again from their current plans
 * (POST /proedit/clips/{id}/render for each). */
export function useRenderVariants() {
  const refresh = useRefreshAfterRun();
  return useMutation({
    mutationFn: (variantIds: number[]) =>
      Promise.all(
        variantIds.map((id) =>
          apiFetch<ProEditStarted>(`/proedit/clips/${id}/render`, {
            method: "POST",
          }),
        ),
      ),
    onSuccess: (started) => Promise.all(started.map(refresh)),
  });
}

/** The runs of variant variantId, newest first
 * (GET /proedit/clips/{id}/runs), loaded again on each mount (a new run
 * may have started); only fetched while enabled. */
export function useProEditRuns(variantId: number, enabled = true) {
  return useQuery({
    queryKey: ["proedit", "runs", variantId],
    queryFn: () => apiFetch<ProEditRun[]>(`/proedit/clips/${variantId}/runs`),
    enabled,
    refetchOnMount: "always",
  });
}

/** Queue the Director again (regenerate, with the last run's options) or
 * the critic on the current plan of variant variantId
 * (POST /proedit/clips/{id}/regenerate or /critic); each ends with a render.
 * Failures (409 while a job runs, a usage cap) are shown by the editor. */
export function useQueueRun(variantId: number, mode: "regenerate" | "critic") {
  const refresh = useRefreshAfterRun();
  return useMutation({
    mutationFn: () =>
      apiFetch<ProEditStarted>(`/proedit/clips/${variantId}/${mode}`, {
        method: "POST",
        silent: true,
      }),
    onSuccess: refresh,
  });
}
