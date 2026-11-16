import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { AgentSetup, ApiKey, ApiKeyCreated } from "./types";

export const apiKeysKey = ["api-keys"] as const;
const agentSetupKey = ["agent-setup"] as const;
// Refresh "last used" now and then, so a newly connected agent shows up.
const KEYS_POLL_MS = 30_000;

/** The API keys of the public API, oldest first (GET /api-keys). */
export function useApiKeys() {
  return useQuery({
    queryKey: apiKeysKey,
    queryFn: () => apiFetch<ApiKey[]>("/api-keys"),
    refetchInterval: KEYS_POLL_MS,
  });
}

/** Make a key (POST /api-keys); the answer is the only time it is shown. */
export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<ApiKeyCreated>("/api-keys", { method: "POST", json: { name } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: apiKeysKey }),
  });
}

/** Revoke a key (DELETE /api-keys/{id}): its requests get 401 from now on. */
export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api-keys/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: apiKeysKey }),
  });
}

/** This app's address and the command of its MCP server (GET /agent-setup). */
export function useAgentSetup() {
  return useQuery({
    queryKey: agentSetupKey,
    queryFn: () => apiFetch<AgentSetup>("/agent-setup"),
    staleTime: Infinity,
  });
}
