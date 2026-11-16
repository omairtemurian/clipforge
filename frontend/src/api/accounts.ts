import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SETUP_DOCS_URL } from "./engines";
import { apiFetch } from "./client";
import type { AccountConnect, PlatformStatus, SocialAccount } from "./types";
import type { SocialPlatform } from "@/lib/platforms";

export const accountsKey = ["accounts"] as const;
const platformsKey = ["accounts", "platforms"] as const;

/** The README section that explains the developer app of a platform. */
export function publishingSetupUrl(platform: SocialPlatform): string {
  return `${SETUP_DOCS_URL}#${platform}-publishing`;
}

const POLL_MS = 2000;

/** Every platform with whether ClipForge can publish to it and whether
 * its developer app keys are set (GET /accounts/platforms). */
export function usePlatforms() {
  return useQuery({
    queryKey: platformsKey,
    queryFn: () => apiFetch<PlatformStatus[]>("/accounts/platforms"),
  });
}

/**
 * The connected accounts (GET /accounts). With `polling` it refreshes every
 * couple of seconds, so a new account shows up when the user finishes the
 * sign-in in the other window.
 */
export function useAccounts(polling = false) {
  return useQuery({
    queryKey: accountsKey,
    queryFn: () => apiFetch<SocialAccount[]>("/accounts"),
    refetchInterval: polling ? POLL_MS : false,
  });
}

/**
 * Start the platform's sign-in (POST /accounts/{platform}/connect) in a new
 * window. The window opens before the request, while the click still counts
 * as a user gesture (popup blockers), and is sent to the platform once the
 * API answers.
 */
export function useConnectAccount() {
  return useMutation({
    mutationFn: async (platform: SocialPlatform) => {
      const popup = window.open("", "_blank");
      try {
        const { authorize_url } = await apiFetch<AccountConnect>(
          `/accounts/${platform}/connect`,
          { method: "POST" },
        );
        if (popup) popup.location.href = authorize_url;
        else window.open(authorize_url, "_blank");
      } catch (error) {
        popup?.close();
        throw error;
      }
    },
  });
}

/** Forget a connected account and its token (DELETE /accounts/{id}); the
 * API refuses while posts wait to be published (409). */
export function useDisconnectAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/accounts/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountsKey }),
  });
}

/** Make an account the one that a one-click post uses on its platform
 * (PUT /accounts/{id}/default). */
export function useSetDefaultAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<SocialAccount>(`/accounts/${id}/default`, { method: "PUT" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountsKey }),
  });
}

/** Set the hashtags that the account's posts always include
 * (PUT /accounts/{id}/hashtags, given without "#"). */
export function useSetAccountHashtags() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, hashtags }: { id: number; hashtags: string[] }) =>
      apiFetch<SocialAccount>(`/accounts/${id}/hashtags`, {
        method: "PUT",
        json: { hashtags },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountsKey }),
  });
}
