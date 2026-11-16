import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { processingDefaultsKey } from "./sources";
import { toast } from "@/lib/toast";
import type { ProcessingPreset, ProcessingSettings } from "./types";

export const processingPresetsKey = ["processing-presets"] as const;

/** The settings panel's saved presets ("My presets"), by name. */
export function useProcessingPresets() {
  return useQuery({
    queryKey: processingPresetsKey,
    queryFn: () =>
      apiFetch<ProcessingPreset[]>("/processing-presets", { silent: true }),
  });
}

/** Save settings as the preset `name`, replacing one of that name. */
export function useSavePreset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (preset: ProcessingPreset) =>
      apiFetch<ProcessingPreset>("/processing-presets", {
        method: "PUT",
        json: preset,
      }),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: processingPresetsKey });
      toast.success(`Saved preset "${saved.name}".`);
    },
  });
}

/** Delete the preset `name`. */
export function useDeletePreset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<void>(`/processing-presets/${encodeURIComponent(name)}`, {
        method: "DELETE",
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: processingPresetsKey }),
  });
}

/** Save settings as the default that the settings panel opens with. */
export function useSaveDefault() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: ProcessingSettings) =>
      apiFetch<ProcessingSettings>("/processing-defaults", {
        method: "PUT",
        json: settings,
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(processingDefaultsKey, saved);
      toast.success("Saved as the default settings.");
    },
  });
}
