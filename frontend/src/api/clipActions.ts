import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import { campaignCheckKey } from "./campaigns";
import { apiFetch } from "./client";
import { projectsKey } from "./projects";
import type {
  Clip,
  ClipPatch,
  Job,
  Project,
  SceneTrack,
  SceneTrackRequest,
  TimelinePatch,
} from "./types";

/** The query key of a clip's version history (GET /clips/{id}/versions). */
export function clipVersionsKey(id: number) {
  return ["clips", id, "versions"] as const;
}

/** Reload the lists of the clip's project, its rule check and its version
 * history (every change of a clip is a version), and set the clip itself. */
export function useStoreClip() {
  const queryClient = useQueryClient();
  return (clip: Clip) => {
    queryClient.setQueryData(["clips", clip.id], clip);
    void queryClient.invalidateQueries({
      queryKey: [...campaignCheckKey, clip.id],
    });
    void queryClient.invalidateQueries({
      queryKey: clipVersionsKey(clip.id),
      exact: true,
    });
    return queryClient.invalidateQueries({
      queryKey: [...projectsKey, clip.project_id, "clips"],
    });
  };
}

/** Save an edited clip (PATCH /clips/{id}) and keep the answer. */
export function useSaveClip(id: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: (patch: ClipPatch) =>
      apiFetch<Clip>(`/clips/${id}`, { method: "PATCH", json: patch }),
    onSuccess: store,
  });
}

/** Save a clip's layer tracks (PATCH /clips/{id}/tracks; null tracks are
 * kept) and keep the answer. */
export function useSaveTracks(id: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: (tracks: TimelinePatch) =>
      apiFetch<Clip>(`/clips/${id}/tracks`, { method: "PATCH", json: tracks }),
    onSuccess: store,
  });
}

/** Let the LLM write the clip's title, description and hashtags again
 * (POST /clips/{id}/regenerate-text, which saves them); keeps the answer. */
export function useRegenerateText(id: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: () =>
      apiFetch<Clip>(`/clips/${id}/regenerate-text`, { method: "POST" }),
    onSuccess: store,
  });
}

/** Track a subject through a scene of the clip (POST
 * /clips/{id}/scenes/track): the crop keyframes that follow it. */
export function useTrackScene(id: number) {
  return useMutation({
    mutationFn: (request: SceneTrackRequest) =>
      apiFetch<SceneTrack>(`/clips/${id}/scenes/track`, {
        method: "POST",
        json: request,
      }),
  });
}

/** Queue a render job for the clip (POST /clips/{id}/render). */
export function useQueueRender(id: number) {
  return useMutation({
    mutationFn: () => apiFetch<Job>(`/clips/${id}/render`, { method: "POST" }),
  });
}

/** Set the brand template of a project's clips (PATCH /projects/{id}). */
export function useSetProjectBrand(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (brandTemplateId: number | null) =>
      apiFetch<Project>(`/projects/${projectId}`, {
        method: "PATCH",
        json: { brand_template_id: brandTemplateId },
      }),
    onSuccess: (project) => {
      queryClient.setQueryData([...projectsKey, projectId], project);
      toast.success("Brand template saved.");
    },
  });
}
