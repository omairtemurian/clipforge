import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import { toast } from "@/lib/toast";
import type {
  LlmModels,
  LlmTestResult,
  SettingsUpdate,
  SettingsView,
} from "./types";

export const appSettingsKey = ["app-settings"] as const;

/** The app settings; API keys only as set or not. */
export function useAppSettings() {
  return useQuery({
    queryKey: appSettingsKey,
    queryFn: () => apiFetch<SettingsView>("/settings"),
  });
}

/** Save the given settings; `onSaved` gets the settings the server returns.
 * With `verifyLlm`, a changed language model is tried first: if it does not
 * answer, the server saves nothing and its error (the provider's) is shown. */
export function useSaveAppSettings(
  onSaved: (saved: SettingsView) => void,
  { verifyLlm = false }: { verifyLlm?: boolean } = {},
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (update: SettingsUpdate) =>
      apiFetch<SettingsView>(
        verifyLlm ? "/settings?verify_llm=true" : "/settings",
        {
          method: "PUT",
          json: update,
        },
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(appSettingsKey, saved);
      toast.success("Settings saved.");
      onSaved(saved);
    },
  });
}

/** Try the LLM with the given settings, without saving them. */
export function useTestLlm() {
  return useMutation({
    mutationFn: (update: SettingsUpdate) =>
      apiFetch<LlmTestResult>("/settings/test-llm", {
        method: "POST",
        json: update,
      }),
  });
}

/** List the models of the provider in the given settings (or the saved
 * ones), without saving them. Failures are shown by the caller. */
export function useLlmModels() {
  return useMutation({
    mutationFn: (update: SettingsUpdate) =>
      apiFetch<LlmModels>("/settings/models", {
        method: "POST",
        json: update,
        silent: true,
      }),
  });
}
