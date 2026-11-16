import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import { apiFetch, apiUrl } from "./client";
import type { Collection, CollectionDetail, Job } from "./types";

const POLL_MS = 3000;

export const collectionsKey = ["collections"] as const;

function refresh(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: collectionsKey });
}

/** Every collection, newest first, with its clip count. */
export function useCollections() {
  return useQuery({
    queryKey: collectionsKey,
    queryFn: () => apiFetch<Collection[]>("/collections"),
  });
}

/** One collection with its clips in order (none while id is null),
 * polled while `poll` says so of it (clips of it are being rendered). */
export function useCollection(
  id: number | null,
  poll: (detail: CollectionDetail) => boolean = () => false,
) {
  return useQuery({
    queryKey: [...collectionsKey, id],
    queryFn: () => apiFetch<CollectionDetail>(`/collections/${id}`),
    enabled: id !== null,
    refetchInterval: (query) =>
      query.state.data && poll(query.state.data) ? POLL_MS : false,
  });
}

/** Queue a render of each clip (POST /clips/{id}/render). */
export function useRenderCollectionClips() {
  return useMutation({
    mutationFn: (clipIds: number[]) =>
      Promise.all(
        clipIds.map((clipId) =>
          apiFetch<Job>(`/clips/${clipId}/render`, { method: "POST" }),
        ),
      ),
    onSuccess: (jobs) =>
      toast.success(
        `Rendering ${jobs.length} ${jobs.length === 1 ? "clip" : "clips"}.`,
      ),
  });
}

/** Make an empty collection (POST /collections). */
export function useCreateCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<CollectionDetail>("/collections", {
        method: "POST",
        json: { name },
      }),
    onSuccess: () => refresh(queryClient),
  });
}

/** Give a collection another name (PATCH /collections/{id}). */
export function useRenameCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      apiFetch<CollectionDetail>(`/collections/${id}`, {
        method: "PATCH",
        json: { name },
      }),
    onSuccess: () => refresh(queryClient),
  });
}

/** Delete a collection; its clips stay (DELETE /collections/{id}). */
export function useDeleteCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/collections/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success(
        "Collection deleted. Its clips are still in their projects.",
      );
      return refresh(queryClient);
    },
  });
}

/** Add clips at the end of a collection (POST /collections/{id}/items). */
export function useAddToCollection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, clipIds }: { id: number; clipIds: number[] }) =>
      apiFetch<CollectionDetail>(`/collections/${id}/items`, {
        method: "POST",
        json: { clip_ids: clipIds },
      }),
    onSuccess: () => refresh(queryClient),
  });
}

/** Take a clip out of a collection (DELETE /collections/{id}/items/{clip}). */
export function useRemoveFromCollection(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (clipId: number) =>
      apiFetch<CollectionDetail>(`/collections/${id}/items/${clipId}`, {
        method: "DELETE",
      }),
    onSuccess: () => refresh(queryClient),
  });
}

/** The zip of a collection's rendered clips with its manifest.json. */
export function collectionZipUrl(id: number): string {
  return apiUrl(`/collections/${id}/download.zip`);
}
