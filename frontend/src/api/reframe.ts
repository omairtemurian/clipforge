import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { ReframePresetInfo } from "./types";

/** The genre reframing presets (GET /reframe-presets). */
export function useReframePresets() {
  return useQuery({
    queryKey: ["reframe-presets"],
    queryFn: () =>
      apiFetch<ReframePresetInfo[]>("/reframe-presets", { silent: true }),
    staleTime: Infinity,
  });
}
