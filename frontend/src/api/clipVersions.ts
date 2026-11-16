import { useMutation, useQuery } from "@tanstack/react-query";
import { clipVersionsKey, useStoreClip } from "./clipActions";
import { apiFetch } from "./client";
import type { Clip, ClipHistory } from "./types";

/** A clip's version history (GET /clips/{id}/versions); silent, since the
 * editor works without it (it only adds undo past the editor's own edits). */
export function useClipVersions(id: number) {
  return useQuery({
    queryKey: clipVersionsKey(id),
    queryFn: () =>
      apiFetch<ClipHistory>(`/clips/${id}/versions`, { silent: true }),
    retry: false,
  });
}

/** A move in a clip's history: undo, redo, or restore of a version. */
export type HistoryMove =
  { type: "undo" } | { type: "redo" } | { type: "restore"; number: number };

function movePath(id: number, move: HistoryMove): string {
  if (move.type === "restore") {
    return `/clips/${id}/versions/${move.number}/restore`;
  }
  return `/clips/${id}/${move.type}`;
}

/** Move the clip in its saved history (POST /clips/{id}/undo, /redo or
 * /versions/{n}/restore); keeps the clip it answers (useStoreClip, which
 * reloads the history). */
export function useMoveClipHistory(id: number) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: (move: HistoryMove) =>
      apiFetch<Clip>(movePath(id, move), { method: "POST" }),
    onSuccess: store,
  });
}
