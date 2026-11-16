import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatBytes } from "@/lib/format";
import { toast } from "@/lib/toast";
import { apiFetch } from "./client";
import { projectsKey } from "./projects";
import type { StorageCleanup, StorageReport } from "./types";

export const storageKey = ["storage"] as const;

/** Every project's disk use, largest first, and the free space. */
export function useStorage() {
  return useQuery({
    queryKey: storageKey,
    queryFn: () => apiFetch<StorageReport>("/storage"),
  });
}

/** Clean up or archive a project's files (POST /projects/{id}/<action>). */
export function useStorageAction(action: "cleanup" | "archive") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: number) =>
      apiFetch<StorageCleanup>(`/projects/${projectId}/${action}`, {
        method: "POST",
      }),
    onSuccess: (result) => {
      const freed = formatBytes(result.freed_bytes);
      toast.success(
        action === "archive"
          ? `Project archived. ${freed} freed.`
          : `Cleaned up. ${freed} freed.`,
      );
      void queryClient.invalidateQueries({ queryKey: projectsKey });
      return queryClient.invalidateQueries({ queryKey: storageKey });
    },
  });
}
