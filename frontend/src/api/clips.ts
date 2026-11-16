import {
  useMutation,
  useQuery,
  useQueryClient,
  type Query,
} from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "@/lib/toast";
import { apiFetch } from "./client";
import { projectsKey } from "./projects";
import type {
  CleanupSuggestion,
  Clip,
  ClipScenes,
  CropTrack,
  Job,
  Project,
  Word,
  ZoomKeyframe,
} from "./types";

const RENDER_POLL_MS = 2000;

/** An output aspect ratio of a clip. */
export type Aspect = CropTrack["aspect"];

function clipsQuery(project: Project, resultSet?: number) {
  const wanted = resultSet ?? project.result_set;
  return {
    queryKey: [
      ...projectsKey,
      project.id,
      "clips",
      project.status,
      wanted,
    ] as const,
    queryFn: () =>
      apiFetch<Clip[]>(
        `/projects/${project.id}/clips${
          resultSet === undefined ? "" : `?result_set=${resultSet}`
        }`,
      ),
    enabled: project.status === "done",
  };
}

/** The clips of a project's result set (the current one unless resultSet is
 * given), best score first; asked only once the project is done. */
export function useClips(project: Project, resultSet?: number) {
  return useQuery(clipsQuery(project, resultSet));
}

/** The number of clips of a project; asked only once it is done. */
export function useClipCount(project: Project) {
  return useQuery({ ...clipsQuery(project), select: (clips) => clips.length });
}

/** The query of one clip (GET /clips/{id}). */
export function clipQuery(id: number) {
  return {
    queryKey: ["clips", id],
    queryFn: () => apiFetch<Clip>(`/clips/${id}`),
  };
}

/** One clip (GET /clips/{id}); refreshed while it renders. */
export function useClip(id: number) {
  return useQuery({
    ...clipQuery(id),
    refetchInterval: (query: Query<Clip>) =>
      query.state.data?.status === "rendering" ? RENDER_POLL_MS : false,
  });
}

/** The words of a saved clip with 30 s of the source around it, in source
 * seconds (GET /clips/{id}/transcript). */
export function useClipTranscript(id: number) {
  return useQuery({
    queryKey: ["clips", id, "transcript"],
    queryFn: () => apiFetch<Word[]>(`/clips/${id}/transcript`),
    staleTime: Infinity,
  });
}

/** The filler and pause cuts polish suggests for clip id over the span
 * start-end (GET /clips/{id}/cleanup-suggestions); asked while enabled. */
export function useCleanupSuggestions(
  id: number,
  span: { start: number; end: number },
  enabled: boolean,
) {
  const { start, end } = span;
  return useQuery({
    queryKey: ["clips", id, "cleanup-suggestions", start, end],
    queryFn: () =>
      apiFetch<CleanupSuggestion[]>(
        `/clips/${id}/cleanup-suggestions?start=${start}&end=${end}`,
      ),
    enabled,
  });
}

/** The silences that auto cut takes out of clip id over the span
 * start-end (GET /clips/{id}/auto-cuts); asked while enabled. */
export function useAutoCuts(
  id: number,
  span: { start: number; end: number },
  enabled: boolean,
) {
  const { start, end } = span;
  return useQuery({
    queryKey: ["clips", id, "auto-cuts", start, end],
    queryFn: () =>
      apiFetch<[number, number][]>(
        `/clips/${id}/auto-cuts?start=${start}&end=${end}`,
      ),
    enabled,
  });
}

/** The punch-ins that auto zoom gives clip id over the span start-end
 * (GET /clips/{id}/auto-zooms); asked while enabled. */
export function useAutoZooms(
  id: number,
  span: { start: number; end: number },
  enabled: boolean,
) {
  const { start, end } = span;
  return useQuery({
    queryKey: ["clips", id, "auto-zooms", start, end],
    queryFn: () =>
      apiFetch<ZoomKeyframe[]>(
        `/clips/${id}/auto-zooms?start=${start}&end=${end}`,
      ),
    enabled,
  });
}

/** The fill window that reframe planned for clip id in aspect (the clip
 * plan's if null), which the crop tool draws (GET /clips/{id}/crop);
 * asked while enabled. */
export function useCropTrack(
  id: number,
  aspect: Aspect | null,
  enabled: boolean,
) {
  const query = aspect ? `?aspect=${encodeURIComponent(aspect)}` : "";
  return useQuery({
    queryKey: ["clips", id, "crop", aspect],
    queryFn: () => apiFetch<CropTrack>(`/clips/${id}/crop${query}`),
    enabled,
    staleTime: Infinity,
  });
}

/** GET /clips/{id}/scenes: the scene cuts of the clip's source (and its
 * scenes as the API sees them). */
export function useClipScenes(id: number) {
  return useQuery({
    queryKey: ["clips", id, "scenes"],
    queryFn: () => apiFetch<ClipScenes>(`/clips/${id}/scenes`),
    staleTime: Infinity,
    retry: false,
  });
}

/** A render or Pro Edit job (which renders a variant) that waits or runs. */
function isRenderActive(job: Job): boolean {
  return (
    (job.kind === "render" || job.kind === "proedit") &&
    (job.status === "queued" || job.status === "running")
  );
}

function pollWhileRendering(query: Query<Job[]>): number | false {
  return query.state.data?.some(isRenderActive) ? RENDER_POLL_MS : false;
}

/**
 * The ids of the clips of a project that a render job is waiting for or
 * working on. The jobs are polled while there are any, and the clips are
 * loaded again whenever the set changes (a render ended or started).
 */
export function useRenderingClipIds(project: Project): Set<number> {
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryKey: [...projectsKey, project.id, "jobs"],
    queryFn: () => apiFetch<Job[]>(`/projects/${project.id}/jobs`),
    refetchInterval: pollWhileRendering,
  });

  const ids = (jobs.data ?? [])
    .filter(isRenderActive)
    .flatMap((job) => (job.clip_id === null ? [] : [job.clip_id]));
  const signature = ids.join(",");

  useEffect(() => {
    void queryClient.invalidateQueries({
      queryKey: [...projectsKey, project.id, "clips"],
    });
  }, [queryClient, project.id, signature]);

  return new Set(ids);
}

/** Queue a render job (POST /clips/{id}/render) for each given clip. */
export function useRenderClips(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (clipIds: number[]) =>
      Promise.all(
        clipIds.map((id) =>
          apiFetch<Job>(`/clips/${id}/render`, { method: "POST" }),
        ),
      ),
    onSuccess: (_jobs, clipIds) => {
      toast.info(
        clipIds.length === 1
          ? "Rendering the clip. Download it when it is ready."
          : `Rendering ${clipIds.length} clips. Download them when they are ready.`,
      );
    },
    onSettled: () =>
      queryClient.invalidateQueries({
        queryKey: [...projectsKey, projectId, "jobs"],
      }),
  });
}

/** Delete a clip (DELETE /clips/{id}) and reload its project's clips. */
export function useDeleteClip(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (clipId: number) =>
      apiFetch<void>(`/clips/${clipId}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Clip removed.");
      return queryClient.invalidateQueries({
        queryKey: [...projectsKey, projectId, "clips"],
      });
    },
  });
}
