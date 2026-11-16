import { useMutation, useQuery } from "@tanstack/react-query";
import { useStoreClip } from "./clipActions";
import { apiFetch } from "./client";
import type { Clip, HookApply, HookEdit, HookTemplateInfo } from "./types";

/** The hook templates (GET /hook-templates); they never change while the
 * app runs. */
export function useHookTemplates() {
  return useQuery({
    queryKey: ["hook-templates"],
    queryFn: () => apiFetch<HookTemplateInfo[]>("/hook-templates"),
    staleTime: Infinity,
  });
}

/** An edit of a clip's viral hook (api/clip_hook). */
export type HookOp =
  | { type: "apply"; body: HookApply }
  | { type: "edit"; body: Partial<HookEdit> }
  | { type: "remove" };

/** An edit of a clip's headline (api/clip_graphics): the text given, or
 * null to have the LLM write one. */
export type HeadlineOp =
  { type: "set"; text: string | null } | { type: "remove" };

/** An edit of a clip's motion graphics (api/clip_graphics). */
export type GraphicsOp =
  { type: "find"; maxItems: number } | { type: "remove" };

/** A request that changes the saved clip and answers it. */
export type ClipRequest = [string, { method: string; json?: unknown }];

function hookRequest(clipId: number, op: HookOp): ClipRequest {
  const path = `/clips/${clipId}/hook`;
  switch (op.type) {
    case "apply":
      return [path, { method: "POST", json: op.body }];
    case "edit":
      return [path, { method: "PATCH", json: op.body }];
    case "remove":
      return [path, { method: "DELETE" }];
  }
}

function headlineRequest(clipId: number, op: HeadlineOp): ClipRequest {
  const path = `/clips/${clipId}/headline`;
  return op.type === "set"
    ? [path, { method: "POST", json: { text: op.text } }]
    : [path, { method: "DELETE" }];
}

function graphicsRequest(clipId: number, op: GraphicsOp): ClipRequest {
  const path = `/clips/${clipId}/motion-graphics`;
  return op.type === "find"
    ? [path, { method: "POST", json: { max_items: op.maxItems } }]
    : [path, { method: "DELETE" }];
}

/** A mutation that sends request(clipId, op) and keeps the clip it answers
 * (useStoreClip), which the caller gives to the editor. */
export function useClipRequest<Op>(
  clipId: number,
  request: (clipId: number, op: Op) => ClipRequest,
) {
  const store = useStoreClip();
  return useMutation({
    mutationFn: (op: Op) => {
      const [path, init] = request(clipId, op);
      return apiFetch<Clip>(path, init);
    },
    onSuccess: store,
  });
}

/** Add, change or remove the hook of clip id (POST/PATCH/DELETE
 * /clips/{id}/hook). */
export function useHookOps(clipId: number) {
  return useClipRequest(clipId, hookRequest);
}

/** Set (given or LLM-written) or remove the headline of clip id (POST/DELETE
 * /clips/{id}/headline). */
export function useHeadlineOps(clipId: number) {
  return useClipRequest(clipId, headlineRequest);
}

/** Find or remove the motion graphics of clip id (POST/DELETE
 * /clips/{id}/motion-graphics). */
export function useGraphicsOps(clipId: number) {
  return useClipRequest(clipId, graphicsRequest);
}
