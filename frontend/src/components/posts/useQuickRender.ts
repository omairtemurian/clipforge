import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useQueueRender } from "@/api/clipActions";
import { clipQuery } from "@/api/clips";
import { projectsKey } from "@/api/projects";
import type { Clip } from "@/api/types";

const POLL_MS = 2000;

export type RenderState = "ready" | "rendering" | "failed";

/**
 * Make sure the clip has its rendered video before it is posted: if it is
 * not rendered, one render is queued on opening and the clip is polled
 * until it is rendered (or failed; `retry` queues it again). The clip's
 * project is told when it is done, so its cards show the new state.
 */
export function useQuickRender(clip: Clip): {
  state: RenderState;
  retry: () => void;
} {
  const queryClient = useQueryClient();
  const queue = useQueueRender(clip.id);
  const started = useRef(false);
  const live = useQuery({
    ...clipQuery(clip.id),
    initialData: clip,
    refetchInterval: (query) =>
      query.state.data?.status === "rendered" ||
      query.state.data?.status === "failed"
        ? false
        : POLL_MS,
  });
  const status = live.data.status;

  useEffect(() => {
    if (started.current || status === "rendered" || status === "rendering") {
      return;
    }
    started.current = true;
    queue.mutate();
  }, [status, queue]);

  useEffect(() => {
    if (status !== "rendered") return;
    void queryClient.invalidateQueries({
      queryKey: [...projectsKey, clip.project_id, "clips"],
    });
  }, [status, queryClient, clip.project_id]);

  const state: RenderState =
    status === "rendered"
      ? "ready"
      : status === "failed"
        ? "failed"
        : "rendering";
  return { state, retry: () => queue.mutate() };
}
