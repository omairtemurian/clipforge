import { useMutation, useQuery } from "@tanstack/react-query";
import { useClipRequest, type ClipRequest } from "./clipGraphics";
import { apiFetch } from "./client";
import type {
  BrollInsert,
  BrollSource,
  BrollSpot,
  BrollSpotsOptions,
  StockProviderStatus,
} from "./types";

/** The stock providers and whether each has an API key (GET
 * /broll/providers). */
export function useBrollProviders() {
  return useQuery({
    queryKey: ["broll", "providers"],
    queryFn: () => apiFetch<StockProviderStatus[]>("/broll/providers"),
  });
}

/** Find the B-roll spots of clip id with stock videos for each (POST
 * /clips/{id}/broll/spots); nothing is saved, so calling it again
 * regenerates them. */
export function useBrollSpots(clipId: number) {
  return useMutation({
    mutationFn: (options: BrollSpotsOptions) =>
      apiFetch<BrollSpot[]>(`/clips/${clipId}/broll/spots`, {
        method: "POST",
        json: options,
      }),
  });
}

/** An edit of a clip's B-roll track (api/broll): put a source on it, make
 * an item show another source or remove an item. */
export type BrollOp =
  | { type: "insert"; body: BrollInsert }
  | { type: "replace"; itemId: string; source: BrollSource }
  | { type: "remove"; itemId: string };

function brollRequest(clipId: number, op: BrollOp): ClipRequest {
  const path = `/clips/${clipId}/broll`;
  switch (op.type) {
    case "insert":
      return [path, { method: "POST", json: op.body }];
    case "replace":
      return [`${path}/${op.itemId}`, { method: "PUT", json: op.source }];
    case "remove":
      return [`${path}/${op.itemId}`, { method: "DELETE" }];
  }
}

/** Insert, replace or remove B-roll of clip id (POST /clips/{id}/broll, PUT
 * and DELETE /clips/{id}/broll/{item}). */
export function useBrollOps(clipId: number) {
  return useClipRequest(clipId, brollRequest);
}
