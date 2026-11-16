import { useMutation } from "@tanstack/react-query";
import { apiFetch, apiUrl } from "./client";
import type { Asset, Post, ThumbnailApply, ThumbnailFrame } from "./types";

/** The JPEG of the clip's rendered video at t seconds. */
export function frameUrl(clipId: number, t: number): string {
  return apiUrl(`/clips/${clipId}/frame?t=${t}`);
}

/** The image of a cover asset. */
export function coverUrl(assetId: number): string {
  return apiUrl(`/thumbnails/${assetId}`);
}

/** Make the frame at t the cover (POST /clips/{id}/thumbnail): an Asset. */
export function usePickFrame(clipId: number) {
  return useMutation({
    mutationFn: (time_s: number) => {
      const body: ThumbnailFrame = { time_s };
      return apiFetch<Asset>(`/clips/${clipId}/thumbnail`, {
        method: "POST",
        json: body,
      });
    },
  });
}

/** Use an uploaded JPEG or PNG as the cover (POST
 * /clips/{id}/thumbnail/upload): an Asset. */
export function useUploadCover(clipId: number) {
  return useMutation({
    mutationFn: (file: File) =>
      apiFetch<Asset>(`/clips/${clipId}/thumbnail/upload`, {
        method: "POST",
        body: file,
      }),
  });
}

/** Set the cover of all the clip's draft and queued posts (POST
 * /clips/{id}/thumbnail/apply). */
export function applyCover(clipId: number, assetId: number): Promise<Post[]> {
  const body: ThumbnailApply = { asset_id: assetId };
  return apiFetch<Post[]>(`/clips/${clipId}/thumbnail/apply`, {
    method: "POST",
    json: body,
  });
}
