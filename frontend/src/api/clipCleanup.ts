import { useMutation, useQuery } from "@tanstack/react-query";
import { useStoreClip } from "./clipActions";
import { apiFetch } from "./client";
import type {
  CleanupApply,
  CleanupOptions,
  CleanupPreview,
  Clip,
  SpeechEnhance,
} from "./types";

/** The codes of the languages that have a filler list (GET
 * /filler-languages); they never change while the app runs. */
export function useFillerLanguages() {
  return useQuery({
    queryKey: ["filler-languages"],
    queryFn: () => apiFetch<string[]>("/filler-languages"),
    staleTime: Infinity,
  });
}

/** What speech cleanup with the options would remove from the saved clip
 * (POST /clips/{id}/cleanup/preview); the clip is unchanged. */
export function usePreviewCleanup(clipId: number) {
  return useMutation({
    mutationFn: (options: CleanupOptions) =>
      apiFetch<CleanupPreview>(`/clips/${clipId}/cleanup/preview`, {
        method: "POST",
        json: options,
      }),
  });
}

/** Cut a preview's items, except the unchecked ones, from the saved clip
 * (POST /clips/{id}/cleanup/apply) and keep the clip it answers. */
export function useApplyCleanup(clipId: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: (body: CleanupApply) =>
      apiFetch<Clip>(`/clips/${clipId}/cleanup/apply`, {
        method: "POST",
        json: body,
      }),
    onSuccess: store,
  });
}

/** Set how strongly the render cleans the clip's speech (PUT
 * /clips/{id}/enhance) and keep the clip it answers. */
export function useSetEnhancement(clipId: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: (body: SpeechEnhance) =>
      apiFetch<Clip>(`/clips/${clipId}/enhance`, { method: "PUT", json: body }),
    onSuccess: store,
  });
}
