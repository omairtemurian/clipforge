import {
  useMutation,
  useQuery,
  useQueryClient,
  type Query,
} from "@tanstack/react-query";
import { forgetUpload, uploadInChunks } from "@/lib/chunkedUpload";
import { activeCount, isActive } from "@/lib/projectStatus";
import { toast } from "@/lib/toast";
import type { RightsChoice } from "@/lib/sourceRights";
import { apiFetch } from "./client";
import type {
  CameraMotionResult,
  DriveFile,
  Job,
  ProcessingSettings,
  Project,
  ZoomOutResult,
} from "./types";

export const projectsKey = ["projects"] as const;

const POLL_MS = 2000;

/** What the user gave: a video link, a video file or a Google Drive video. */
export type VideoSource =
  { url: string } | { file: File } | { drive: DriveFile };

/** A new project: its video and how to process it. */
export interface NewProject {
  source: VideoSource;
  settings: ProcessingSettings;
  rights: RightsChoice;
  /** Called while a file uploads with the share sent, 0 to 1. */
  onUploadProgress?: (fraction: number) => void;
}

function pollWhileActive(query: Query<Project[]>): number | false {
  return query.state.data?.some(isActive) ? POLL_MS : false;
}

/** Every project, newest first; refreshed while one is queued or running. */
export function useProjects() {
  return useQuery({
    queryKey: projectsKey,
    queryFn: () => apiFetch<Project[]>("/projects"),
    refetchInterval: pollWhileActive,
  });
}

/** The number of queued or running projects (the sidebar badge). */
export function useActiveProjectCount() {
  return useQuery({
    queryKey: projectsKey,
    queryFn: () => apiFetch<Project[]>("/projects"),
    refetchInterval: pollWhileActive,
    select: activeCount,
  });
}

/** One project; refreshed while it is queued or running. */
export function useProject(id: number) {
  return useQuery({
    queryKey: [...projectsKey, id],
    queryFn: () => apiFetch<Project>(`/projects/${id}`),
    refetchInterval: (query: Query<Project>) =>
      query.state.data && isActive(query.state.data) ? POLL_MS : false,
  });
}

/** Mark a finished project as opened (POST /projects/{id}/open): its "New"
 * badge goes away. */
export function useOpenProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<Project>(`/projects/${id}/open`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectsKey }),
  });
}

/** Upload file in resumable chunks, then make it a project
 * (POST /uploads/{id}/complete). */
async function addUploadedFile(
  file: File,
  { settings, rights, onUploadProgress }: Omit<NewProject, "source">,
): Promise<Project> {
  const uploadId = await uploadInChunks(file, {
    onProgress: (sent, total) => onUploadProgress?.(sent / total),
  });
  const created = await apiFetch<Project>(`/uploads/${uploadId}/complete`, {
    method: "POST",
    json: { settings, ...rights },
  });
  forgetUpload(file);
  return created;
}

/** Create a project from a link (POST /projects), a Drive video (POST
 * /sources/gdrive/import) or a file (chunked upload), with its processing
 * settings and source rights. */
export function useAddProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ source, ...rest }: NewProject) => {
      if ("url" in source) {
        return apiFetch<Project>("/projects", {
          method: "POST",
          json: { url: source.url, settings: rest.settings, ...rest.rights },
        });
      }
      if ("drive" in source) {
        return apiFetch<Project>("/sources/gdrive/import", {
          method: "POST",
          json: {
            file: source.drive.id,
            settings: rest.settings,
            ...rest.rights,
          },
        });
      }
      return addUploadedFile(source.file, rest);
    },
    onSuccess: () => {
      toast.success("Video added. ClipForge is looking for clips.");
      return queryClient.invalidateQueries({ queryKey: projectsKey });
    },
  });
}

/** Process a failed project again (POST /projects/{id}/reprocess); it
 * resumes after the last step it finished. */
export function useReprocessProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<Job>(`/projects/${id}/reprocess`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Processing the video again.");
      return queryClient.invalidateQueries({ queryKey: projectsKey });
    },
  });
}

/** Give a project another title (PATCH /projects/{id}). */
export function useRenameProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) =>
      apiFetch<Project>(`/projects/${id}`, {
        method: "PATCH",
        json: { title },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: projectsKey }),
  });
}

/** Save a project's zoom-out moments intensity and plan the zoom-outs of
 * its clips that have no manual scenes again (PUT /projects/{id}/zoom-out);
 * the rendered videos change once the clips are rendered. */
export function useSetZoomOut(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (intensity: ProcessingSettings["zoom_out_moments"]) =>
      apiFetch<ZoomOutResult>(`/projects/${id}/zoom-out`, {
        method: "PUT",
        json: { intensity },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectsKey });
      await queryClient.invalidateQueries({ queryKey: ["clips"] });
    },
  });
}

/** Save how a project's auto-tracking windows move and plan its clips'
 * windows again with it (PUT /projects/{id}/camera-motion); the rendered
 * videos change once the clips are rendered. */
export function useSetCameraMotion(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (camera_motion: ProcessingSettings["camera_motion"]) =>
      apiFetch<CameraMotionResult>(`/projects/${id}/camera-motion`, {
        method: "PUT",
        json: { camera_motion },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: projectsKey });
      await queryClient.invalidateQueries({ queryKey: ["clips"] });
    },
  });
}

/** Delete a project with its clips and files (DELETE /projects/{id}). */
export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/projects/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Project deleted.");
      return queryClient.invalidateQueries({ queryKey: projectsKey });
    },
  });
}

/** Ask the LLM again for the clips of a finished project with a new prompt
 * (POST /projects/{id}/reprompt); the project is queued until done. */
export function useReprompt(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (prompt: string) =>
      apiFetch<Job>(`/projects/${id}/reprompt`, {
        method: "POST",
        json: { prompt },
      }),
    onSuccess: () => {
      toast.success("ClipForge is looking for new clips.");
      return queryClient.invalidateQueries({ queryKey: projectsKey });
    },
  });
}
