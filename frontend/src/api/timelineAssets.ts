import { useQuery } from "@tanstack/react-query";
import type { ClipRange } from "@/lib/timeline";
import type { FilmstripStrip } from "@/lib/timelineMedia";
import { apiFetch, apiUrl } from "./client";
import type { Waveform } from "./types";

/** A filmstrip as loaded: its image as a Blob, to show by object URL. */
export type FilmstripData = FilmstripStrip & { image: Blob };

function header(response: Response, name: string): number {
  const value = Number(response.headers.get(name));
  if (!Number.isFinite(value)) throw new Error(`bad ${name} header`);
  return value;
}

/** Load a clip's filmstrip with the tile layout of its headers. */
async function fetchFilmstrip(clipId: number): Promise<FilmstripData> {
  const response = await fetch(apiUrl(`/clips/${clipId}/filmstrip`));
  if (!response.ok) throw new Error(`filmstrip: ${response.status}`);
  const count = header(response, "X-Filmstrip-Count");
  const image = await response.blob();
  const bitmap = await createImageBitmap(image);
  const tileAspect = bitmap.width / count / bitmap.height;
  bitmap.close();
  return {
    image,
    start: header(response, "X-Filmstrip-Start"),
    interval: header(response, "X-Filmstrip-Interval"),
    count,
    tileAspect,
  };
}

/**
 * The filmstrip of the source over a saved clip with 30 s around it (GET
 * /clips/{id}/filmstrip); span is the saved clip, so a saved edit loads a
 * new one. Failures leave the video row empty, without a toast.
 */
export function useFilmstrip(clipId: number, span: ClipRange) {
  return useQuery({
    queryKey: ["clips", clipId, "filmstrip", span.start, span.end],
    queryFn: () => fetchFilmstrip(clipId),
    staleTime: Infinity,
    retry: false,
  });
}

/** The audio peaks over a saved clip with 30 s around it (GET
 * /clips/{id}/waveform); failures leave the audio row empty. */
export function useWaveform(clipId: number, span: ClipRange) {
  return useQuery({
    queryKey: ["clips", clipId, "waveform", span.start, span.end],
    queryFn: () =>
      apiFetch<Waveform>(`/clips/${clipId}/waveform`, { silent: true }),
    staleTime: Infinity,
    retry: false,
  });
}
