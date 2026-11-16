import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import { apiFetch, apiUrl } from "./client";
import type { MediaItem } from "./types";

export const mediaLibraryKey = ["library"] as const;

/** The media library's files (GET /library), in id order. */
export function useMediaLibrary() {
  return useQuery({
    queryKey: mediaLibraryKey,
    queryFn: () => apiFetch<MediaItem[]>("/library"),
  });
}

/** Add a file to the media library (POST /library, multipart); the API
 * finds its kind from its first bytes. */
export function useUploadMedia() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch<MediaItem>("/library", { method: "POST", body: form });
    },
    onSuccess: async (media) => {
      await queryClient.invalidateQueries({ queryKey: mediaLibraryKey });
      toast.success(`Added "${media.name}" to the media library.`);
    },
  });
}

/** The URL of a library file's thumbnail (a picture, a video frame or the
 * audio's waveform). */
export function mediaThumbnailUrl(assetId: number): string {
  return apiUrl(`/library/${assetId}/thumbnail`);
}
