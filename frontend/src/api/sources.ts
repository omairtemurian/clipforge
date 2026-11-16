import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  ProcessingSettings,
  SourceInfo,
  SpeechLanguage,
  SubtitlesUpload,
} from "./types";

export const processingDefaultsKey = ["processing-defaults"] as const;

/** The settings a new project gets by default: the saved default, or the
 * server's config. */
export function useProcessingDefaults() {
  return useQuery({
    queryKey: processingDefaultsKey,
    queryFn: () => apiFetch<ProcessingSettings>("/processing-defaults"),
    staleTime: Infinity,
  });
}

/**
 * Title, duration and thumbnail of a video link (POST /sources/probe).
 * Disabled for null; errors are not toasted: the settings panel shows them.
 */
export function useLinkInfo(url: string | null) {
  return useQuery({
    queryKey: ["source-info", url],
    queryFn: () =>
      apiFetch<SourceInfo>("/sources/probe", {
        method: "POST",
        json: { url },
        silent: true,
      }),
    enabled: url !== null,
    staleTime: Infinity,
    retry: false,
  });
}

/** The languages Whisper can transcribe, by name (GET /speech-languages). */
export function useSpeechLanguages() {
  return useQuery({
    queryKey: ["speech-languages"],
    queryFn: () =>
      apiFetch<SpeechLanguage[]>("/speech-languages", { silent: true }),
    staleTime: Infinity,
  });
}

/** Upload an SRT or VTT file to use as a new project's transcript (POST /subtitles). */
export function uploadSubtitles(file: File): Promise<SubtitlesUpload> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<SubtitlesUpload>("/subtitles", {
    method: "POST",
    body: form,
  });
}
