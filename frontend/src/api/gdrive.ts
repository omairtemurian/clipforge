import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SETUP_DOCS_URL } from "./engines";
import { apiFetch } from "./client";
import type { DriveConnect, DriveFile, DriveStatus } from "./types";

export const driveKey = ["gdrive"] as const;

/** The README section that explains the Google OAuth credentials. */
export const DRIVE_SETUP_URL = `${SETUP_DOCS_URL}#google-drive-import`;

const POLL_MS = 2000;

/**
 * Whether Google Drive is configured and connected (GET /sources/gdrive).
 * Polled while configured but not connected, so the dialog notices when the
 * user finishes the Google consent in the other window.
 */
export function useDriveStatus() {
  return useQuery({
    queryKey: driveKey,
    queryFn: () => apiFetch<DriveStatus>("/sources/gdrive", { silent: true }),
    refetchInterval: (query) => {
      const status = query.state.data;
      return status?.configured && !status.connected ? POLL_MS : false;
    },
  });
}

/**
 * Start the Google consent (POST /sources/gdrive/connect) in a new window.
 *
 * The window opens before the request, while the click still counts as a
 * user gesture (popup blockers), and is sent to Google once the API answers.
 */
export function useConnectDrive() {
  return useMutation({
    mutationFn: async () => {
      const popup = window.open("", "_blank");
      try {
        const { authorize_url } = await apiFetch<DriveConnect>(
          "/sources/gdrive/connect",
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

/** Forget the connected Google account (DELETE /sources/gdrive/connection). */
export function useDisconnectDrive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<void>("/sources/gdrive/connection", { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: driveKey }),
  });
}

/** Look up a Drive video by link or id (POST /sources/gdrive/file); the
 * dialog shows the error itself. */
export function useDriveFile() {
  return useMutation({
    mutationFn: (file: string) =>
      apiFetch<DriveFile>("/sources/gdrive/file", {
        method: "POST",
        json: { file },
        silent: true,
      }),
  });
}
