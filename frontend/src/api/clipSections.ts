import { useMutation, useQuery } from "@tanstack/react-query";
import { useStoreClip } from "./clipActions";
import { apiFetch } from "./client";
import type { Clip, Transcript } from "./types";

/** The transcript of a project's source video (GET
 * /projects/{id}/transcript), which the add-section picker lists; asked
 * while enabled. */
export function useSourceTranscript(projectId: number, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", projectId, "source-transcript"],
    queryFn: () => apiFetch<Transcript>(`/projects/${projectId}/transcript`),
    enabled,
    staleTime: Infinity,
  });
}

/** An edit of a clip's sections (api/clip_sections). */
export type SectionOp =
  | { type: "add"; start: number; end: number }
  | { type: "split"; at: number }
  | { type: "reorder"; order: number[] }
  | { type: "delete"; index: number };

function sectionRequest(
  clipId: number,
  op: SectionOp,
): [string, { method: string; json?: unknown }] {
  const base = `/clips/${clipId}/sections`;
  switch (op.type) {
    case "add":
      return [base, { method: "POST", json: { start: op.start, end: op.end } }];
    case "split":
      return [`${base}/split`, { method: "POST", json: { at: op.at } }];
    case "reorder":
      return [`${base}/reorder`, { method: "POST", json: { order: op.order } }];
    case "delete":
      return [`${base}/${op.index}`, { method: "DELETE" }];
  }
}

/** Edit the sections of clip id (POST/DELETE /clips/{id}/sections...); keeps
 * the clip it answers (useStoreClip), which the caller gives to the editor. */
export function useSectionOps(clipId: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: (op: SectionOp) => {
      const [path, init] = sectionRequest(clipId, op);
      return apiFetch<Clip>(path, init);
    },
    onSuccess: store,
  });
}

/** A copy of a clip: a duplicate, or the clip split in two at a source time. */
export type CopyOp = { type: "duplicate" } | { type: "split"; at: number };

/** Duplicate clip id or split it in two (POST /clips/{id}/duplicate and
 * /split); answers the new clip and, for a split, the first part (the clip
 * itself, changed), which it keeps. */
export function useCopyClip(clipId: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: async (op: CopyOp): Promise<{ made: Clip; first?: Clip }> => {
      if (op.type === "duplicate") {
        const made = await apiFetch<Clip>(`/clips/${clipId}/duplicate`, {
          method: "POST",
        });
        return { made };
      }
      const [first, made] = await apiFetch<[Clip, Clip]>(
        `/clips/${clipId}/split`,
        { method: "POST", json: { at: op.at } },
      );
      return { made, first };
    },
    onSuccess: ({ made, first }) => {
      if (first) void store(first);
      return store(made);
    },
  });
}
