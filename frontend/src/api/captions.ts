/**
 * The caption tools of the editor (SPEC-v2 3.4): uploaded fonts, the caption
 * translation of a clip, the custom censor list, the brand vocabulary with
 * "replace everywhere", the live preview of a caption style and the
 * transcript and subtitle downloads.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import { useStoreClip } from "./clipActions";
import { ApiError, apiFetch, apiUrl } from "./client";
import { projectsKey } from "./projects";
import type {
  CaptionStyle,
  CensorWords,
  Clip,
  FontFile,
  ReplaceRequest,
  ReplaceResult,
  Vocabulary,
} from "./types";

const brandFontsKey = ["brand-fonts"] as const;
const vocabularyKey = ["vocabulary"] as const;
const censorWordsKey = ["censor-words"] as const;

/** Add a TTF or OTF font to the library (POST /fonts); the font names
 * (GET /brand-fonts) are loaded again. */
export function useUploadFont() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch<FontFile>("/fonts", { method: "POST", body: form });
    },
    onSuccess: async (font) => {
      await queryClient.invalidateQueries({ queryKey: brandFontsKey });
      toast.success(`Added the font "${font.names[0] ?? "font"}".`);
    },
  });
}

/** Translate the clip's captions into language (a Whisper code) and keep
 * the clip the API answers with. */
export function useTranslateCaptions(clipId: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: (language: string) =>
      apiFetch<Clip>(`/clips/${clipId}/caption-translation`, {
        method: "POST",
        json: { language },
      }),
    onSuccess: store,
  });
}

/** Remove the clip's caption translation and keep the clip. */
export function useRemoveTranslation(clipId: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: () =>
      apiFetch<Clip>(`/clips/${clipId}/caption-translation`, {
        method: "DELETE",
      }),
    onSuccess: store,
  });
}

/** The custom censor list (GET /censor-words). */
export function useCensorWords() {
  return useQuery({
    queryKey: censorWordsKey,
    queryFn: () => apiFetch<CensorWords>("/censor-words"),
  });
}

/** Save the custom censor list (PUT /censor-words). */
export function useSaveCensorWords(onSaved: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (words: CensorWords) =>
      apiFetch<CensorWords>("/censor-words", { method: "PUT", json: words }),
    onSuccess: (saved) => {
      queryClient.setQueryData(censorWordsKey, saved);
      toast.success("Saved the censor list.");
      onSaved();
    },
  });
}

/** The brand vocabulary (GET /vocabulary). */
export function useVocabulary() {
  return useQuery({
    queryKey: vocabularyKey,
    queryFn: () => apiFetch<Vocabulary>("/vocabulary"),
  });
}

/** Save the brand vocabulary (PUT /vocabulary). */
export function useSaveVocabulary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vocabulary: Vocabulary) =>
      apiFetch<Vocabulary>("/vocabulary", { method: "PUT", json: vocabulary }),
    onSuccess: (saved) => {
      queryClient.setQueryData(vocabularyKey, saved);
      toast.success("Saved the vocabulary.");
    },
  });
}

/** Replace words in the project's transcript and every clip of it, then
 * load its clips and transcripts again; onDone gets the result. */
export function useReplaceEverywhere(
  projectId: number,
  onDone: (result: ReplaceResult) => void,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: ReplaceRequest) =>
      apiFetch<ReplaceResult>(`/projects/${projectId}/replace-everywhere`, {
        method: "POST",
        json: request,
      }),
    onSuccess: async (result, request) => {
      if (request.remember) {
        await queryClient.invalidateQueries({ queryKey: vocabularyKey });
      }
      await queryClient.invalidateQueries({ queryKey: ["clips"] });
      await queryClient.invalidateQueries({
        queryKey: [...projectsKey, projectId, "clips"],
      });
      onDone(result);
    },
  });
}

/** A PNG of template name's sample caption with style applied (POST
 * /caption-templates/{name}/preview), as a Blob. */
export async function fetchCaptionPreview(
  name: string,
  style: CaptionStyle,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await fetch(apiUrl(`/caption-templates/${name}/preview`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(style),
    signal,
  });
  if (!response.ok) {
    throw new ApiError(response.status, "preview", "No caption preview.");
  }
  return response.blob();
}

export type TranscriptFormat = "txt" | "srt" | "vtt";

/** The URL of a transcript download: a clip's captions or the whole
 * transcript of a project's source video, as text or subtitles. */
export function transcriptUrl(
  of: "clips" | "projects",
  id: number,
  format: TranscriptFormat,
): string {
  return apiUrl(`/${of}/${id}/transcript.${format}`);
}
