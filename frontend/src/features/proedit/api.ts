import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { Clip, ProEditStatus } from "@/api/types";

export const proEditStatusKey = ["proedit", "status"] as const;

/** Whether Pro Edit is available: GET /proedit/status answers when
 * proedit.enabled is on and 404 proedit_disabled when it is off; any
 * failure counts as off. `pending` is true until the server answered. */
export function useProEditEnabled(): { enabled: boolean; pending: boolean } {
  const status = useQuery({
    queryKey: proEditStatusKey,
    queryFn: () => apiFetch<ProEditStatus>("/proedit/status", { silent: true }),
    staleTime: Infinity,
  });
  return {
    enabled: status.data?.enabled === true,
    pending: status.isPending,
  };
}

/** The Pro Edit variants of clip clipId, oldest first
 * (GET /proedit/clips/{id}/variants). */
export function useProEditVariants(clipId: number) {
  return useQuery({
    queryKey: ["proedit", "variants", clipId],
    queryFn: () => apiFetch<Clip[]>(`/proedit/clips/${clipId}/variants`),
  });
}
