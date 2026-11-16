import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import { apiFetch } from "./client";
import { projectsKey } from "./projects";
import type { Chapter, Job } from "./types";

function chaptersKey(projectId: number) {
  return [...projectsKey, projectId, "chapters"] as const;
}

/** The topic chapters of a project in order, none until they are made
 * (GET /projects/{id}/chapters). */
export function useChapters(projectId: number) {
  return useQuery({
    queryKey: chaptersKey(projectId),
    queryFn: () => apiFetch<Chapter[]>(`/projects/${projectId}/chapters`),
  });
}

/** Let the LLM divide the project's transcript into topics
 * (POST /projects/{id}/chapters); the answer replaces the chapters. */
export function useMakeChapters(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<Chapter[]>(`/projects/${projectId}/chapters`, {
        method: "POST",
      }),
    onSuccess: (chapters) => {
      queryClient.setQueryData(chaptersKey(projectId), chapters);
    },
  });
}

/** Clip only the chosen chapters, with an optional prompt
 * (POST /projects/{id}/clip-by-topic); the project is queued until done. */
export function useClipByTopic(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { chapters: number[]; prompt: string | null }) =>
      apiFetch<Job>(`/projects/${projectId}/clip-by-topic`, {
        method: "POST",
        json: body,
      }),
    onSuccess: () => {
      toast.success("ClipForge is looking for clips in those topics.");
      return queryClient.invalidateQueries({ queryKey: projectsKey });
    },
  });
}
