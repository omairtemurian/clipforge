import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { Clip, Job, SearchHit } from "./types";

export const RESULT_LIMIT = 50;

/** What the Library searches: the words and, optionally, one project. */
export interface LibraryQuery {
  q: string;
  projectId: number | null;
}

/** The GET /search path of a library query. */
export function searchPath({ q, projectId }: LibraryQuery): string {
  const params = new URLSearchParams({ q, limit: String(RESULT_LIMIT) });
  if (projectId !== null) params.set("project_id", String(projectId));
  return `/search?${params.toString()}`;
}

/** The transcript segments that match the query, best first (none for ""). */
export function useLibrarySearch(query: LibraryQuery) {
  return useQuery({
    queryKey: ["search", query.q, query.projectId],
    queryFn: () => apiFetch<SearchHit[]>(searchPath(query)),
    enabled: query.q.trim() !== "",
  });
}

/** A moment to make a clip of: a hit's project and start, and a length. */
export interface Moment {
  projectId: number;
  at: number;
  length: number;
}

/** Make a clip from a moment (POST /search/clips) and queue its render. */
export async function clipFromMoment(moment: Moment): Promise<Clip> {
  const clip = await apiFetch<Clip>("/search/clips", {
    method: "POST",
    json: {
      project_id: moment.projectId,
      at: moment.at,
      length: moment.length,
    },
  });
  await apiFetch<Job>(`/clips/${clip.id}/render`, { method: "POST" });
  return clip;
}

/** Make and render a clip from one moment. */
export function useClipFromMoment() {
  return useMutation({ mutationFn: clipFromMoment });
}
