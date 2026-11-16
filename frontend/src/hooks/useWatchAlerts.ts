import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchEventsAfter, watchEventsKey } from "@/api/watch";
import { watchedChannelsKey } from "@/api/autoImport";
import { showDesktopAlert } from "@/lib/desktopAlerts";
import { toast } from "@/lib/toast";
import { alertText } from "@/lib/watch";

export const ALERT_POLL_MS = 10_000;

/**
 * Alert on every new upload or go-live of a watched creator, on any page:
 * poll GET /watch/events?after=<last id> every intervalMs and show each new
 * alert as a toast and (if allowed) a desktop notification. The first
 * answer is the baseline, so alerts from before the app opened stay quiet.
 */
export function useWatchAlerts(intervalMs: number = ALERT_POLL_MS) {
  const queryClient = useQueryClient();

  useEffect(() => {
    let last: number | null = null;
    let cancelled = false;

    async function check() {
      try {
        const events = await fetchEventsAfter(last ?? 0);
        if (cancelled) return;
        const newest = Math.max(last ?? 0, ...events.map((event) => event.id));
        if (last !== null && events.length > 0) {
          for (const event of [...events].reverse()) {
            const { title, body } = alertText(event);
            toast.info(`${title}: ${body}`);
            showDesktopAlert(title, body);
          }
          void queryClient.invalidateQueries({ queryKey: watchEventsKey });
          void queryClient.invalidateQueries({ queryKey: watchedChannelsKey });
        }
        last = newest;
      } catch {
        // Offline or the server restarting: the next check tries again.
      }
    }

    void check();
    const timer = setInterval(() => void check(), intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs, queryClient]);
}
