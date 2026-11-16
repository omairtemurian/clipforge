import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { EdlItem, ProEditPlan, ProEditTiming } from "@/api/types";

const planKey = (variantId: number) => ["proedit", "plan", variantId] as const;
const timingKey = (variantId: number) =>
  ["proedit", "timing", variantId] as const;

/** The current plan of variant variantId (GET /proedit/clips/{id}/plan);
 * a variant without a plan yet answers 404 no_plan, shown by the editor,
 * not as a toast. */
export function useProEditPlan(variantId: number) {
  return useQuery({
    queryKey: planKey(variantId),
    queryFn: () =>
      apiFetch<ProEditPlan>(`/proedit/clips/${variantId}/plan`, {
        silent: true,
      }),
    retry: false,
  });
}

/** Every plan version of variant variantId, oldest first
 * (GET /proedit/clips/{id}/plans). */
export function useProEditPlans(variantId: number) {
  return useQuery({
    queryKey: ["proedit", "plans", variantId] as const,
    queryFn: () =>
      apiFetch<ProEditPlan[]>(`/proedit/clips/${variantId}/plans`, {
        silent: true,
      }),
  });
}

/** What the items of variant variantId snap to: frame rate, length, words
 * and plan beats (GET /proedit/clips/{id}/timing). */
export function useProEditTiming(variantId: number) {
  return useQuery({
    queryKey: timingKey(variantId),
    queryFn: () =>
      apiFetch<ProEditTiming>(`/proedit/clips/${variantId}/timing`, {
        silent: true,
      }),
  });
}

/** Load the variant, its plan, timing and runs again (a job of it ended). */
export function useReloadVariant(variantId: number) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["clips", variantId] });
    for (const part of ["plan", "plans", "timing", "runs"]) {
      void queryClient.invalidateQueries({
        queryKey: ["proedit", part, variantId],
      });
    }
  };
}

/** Store edited items as the next plan version of variant variantId
 * (PATCH /proedit/clips/{id}/plan); the new plan replaces the cached one
 * and the timing (its beds' beats) loads again. Failures (422 with the
 * problems in the message, 409 while a job runs) are shown by the editor. */
export function usePatchPlan(variantId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (items: EdlItem[]) =>
      apiFetch<ProEditPlan>(`/proedit/clips/${variantId}/plan`, {
        method: "PATCH",
        json: { items },
        silent: true,
      }),
    onSuccess: (plan) => {
      queryClient.setQueryData(planKey(variantId), plan);
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: timingKey(variantId) }),
        queryClient.invalidateQueries({
          queryKey: ["proedit", "plans", variantId],
        }),
      ]);
    },
  });
}

/** Store a copy of plan version 1 as the next version of variant variantId
 * (POST /proedit/clips/{id}/reset); like a patch, the new plan replaces the
 * cached one. Failures are shown by the editor. */
export function useResetPlan(variantId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<ProEditPlan>(`/proedit/clips/${variantId}/reset`, {
        method: "POST",
        silent: true,
      }),
    onSuccess: (plan) => {
      queryClient.setQueryData(planKey(variantId), plan);
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: timingKey(variantId) }),
        queryClient.invalidateQueries({
          queryKey: ["proedit", "plans", variantId],
        }),
      ]);
    },
  });
}
