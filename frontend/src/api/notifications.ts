import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  Notification,
  NotificationChannels,
  NotificationList,
} from "./types";

export const notificationsKey = ["notifications"] as const;
export const channelsKey = ["notifications", "channels"] as const;

const POLL_MS = 15_000;

/** The newest notifications and the unread count; refreshed every 15 s so
 * the bell shows what happened while the page was open. */
export function useNotifications() {
  return useQuery({
    queryKey: notificationsKey,
    queryFn: () => apiFetch<NotificationList>("/notifications"),
    refetchInterval: POLL_MS,
  });
}

/** Whether notifications are also emailed (and to whom) and shown on the
 * desktop (GET /notifications/channels). */
export function useNotificationChannels() {
  return useQuery({
    queryKey: channelsKey,
    queryFn: () => apiFetch<NotificationChannels>("/notifications/channels"),
  });
}

/** Mark one notification read. */
export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<Notification>(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: notificationsKey }),
  });
}

/** Mark every notification read. */
export function useMarkAllRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<NotificationList>("/notifications/read-all", {
        method: "POST",
      }),
    onSuccess: (list) => queryClient.setQueryData(notificationsKey, list),
  });
}

/** Make a test notification, to try the email and desktop channels. */
export function useSendTestNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<Notification>("/notifications/test", { method: "POST" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: notificationsKey }),
  });
}
