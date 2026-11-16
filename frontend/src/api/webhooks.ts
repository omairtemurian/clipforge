import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { Webhook, WebhookCreate, WebhookCreated } from "./types";

export const webhooksKey = ["webhooks"] as const;

/** The registered webhooks, without their secrets (GET /webhooks). */
export function useWebhooks() {
  return useQuery({
    queryKey: webhooksKey,
    queryFn: () => apiFetch<Webhook[]>("/webhooks"),
  });
}

/** Register a webhook (POST /webhooks); the answer holds its signing
 * secret, shown this once. */
export function useCreateWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: WebhookCreate) =>
      apiFetch<WebhookCreated>("/webhooks", { method: "POST", json: body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: webhooksKey }),
  });
}

/** Delete a webhook and its delivery log (DELETE /webhooks/{id}). */
export function useDeleteWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/webhooks/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: webhooksKey }),
  });
}
