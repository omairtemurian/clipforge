import { useQuery } from "@tanstack/react-query";
import { useClipRequest, type ClipRequest } from "./clipGraphics";
import { apiFetch, apiUrl } from "./client";
import type { MusicTrack, SfxSound } from "./types";

/** The music library (GET /music): bundled loops first, then uploads. */
export function useMusicLibrary() {
  return useQuery({
    queryKey: ["music"],
    queryFn: () => apiFetch<MusicTrack[]>("/music"),
  });
}

/** The bundled sound effect pack (GET /sfx). */
export function useSfxPack() {
  return useQuery({
    queryKey: ["sfx"],
    queryFn: () => apiFetch<SfxSound[]>("/sfx"),
  });
}

/** The URL of a music track's file, to listen to. */
export function musicFileUrl(assetId: number): string {
  return apiUrl(`/music/${assetId}/file`);
}

/** The URL of a sound effect's file, to listen to. */
export function sfxFileUrl(assetId: number): string {
  return apiUrl(`/sfx/${assetId}/file`);
}

/** Place sound effects on clip id with the AI, at most maxItems (POST
 * /clips/{id}/auto-sfx); the clip it answers is kept. */
export function useAutoSfx(clipId: number) {
  return useClipRequest(clipId, (id, maxItems: number): ClipRequest => [
    `/clips/${id}/auto-sfx`,
    { method: "POST", json: { max_items: maxItems } },
  ]);
}
