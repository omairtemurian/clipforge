import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { projectsKey } from "./projects";
import type { Job } from "./types";

const POLL_MS = 2000;

/** The kinds of job that make a project's clips: the first run and a reprompt. */
const CLIPPING_KINDS: readonly string[] = ["process", "reprompt"];

/**
 * The process or reprompt job of a project (the newest one), or undefined if
 * it has none.
 * With `poll` it is fetched again every 2 s (a card of a running project);
 * `enabled: false` does not fetch it at all.
 */
export function useProcessJob(
  projectId: number,
  { poll = false, enabled = true }: { poll?: boolean; enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [...projectsKey, projectId, "jobs"],
    queryFn: () => apiFetch<Job[]>(`/projects/${projectId}/jobs`),
    select: (jobs) => jobs.find((job) => CLIPPING_KINDS.includes(job.kind)),
    refetchInterval: poll ? POLL_MS : false,
    enabled,
  });
}
