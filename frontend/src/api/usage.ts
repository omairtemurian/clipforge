import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { UsageSummary } from "./types";

export const usageKey = ["usage"] as const;

/** The usage meter of the current month: totals per kind and project, with
 * the monthly caps (GET /usage). */
export function useUsage() {
  return useQuery({
    queryKey: usageKey,
    queryFn: () => apiFetch<UsageSummary>("/usage"),
  });
}
