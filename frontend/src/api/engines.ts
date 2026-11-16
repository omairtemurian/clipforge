import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { EngineStatus } from "./types";

export const enginesKey = ["engines"] as const;

/** Where each engine's setup section is (its `doc_anchor` is a heading id). */
export const SETUP_DOCS_URL = "https://github.com/omairtemurian/clipforge";

/** The setup section of an engine in the README. */
export function setupUrl(engine: EngineStatus): string {
  return `${SETUP_DOCS_URL}#${engine.doc_anchor}`;
}

/** The optional engines and whether each is installed (GET /engines). The
 * server caches the checks; `recheck` asks it to run them again. */
export function useEngines() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: enginesKey,
    queryFn: () => apiFetch<EngineStatus[]>("/engines"),
    staleTime: 60_000,
  });
  const recheck = useMutation({
    mutationFn: () => apiFetch<EngineStatus[]>("/engines?refresh=true"),
    onSuccess: (fresh) => queryClient.setQueryData(enginesKey, fresh),
  });
  return { ...query, recheck };
}
