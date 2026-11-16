import { useEffect, useRef } from "react";
import { handleInboxKey, type InboxKeyHandlers } from "@/lib/drafts";

/** Listen for the Approval Inbox's keys (handleInboxKey) while enabled; the
 * latest handlers are always used. */
export function useInboxShortcuts(
  handlers: InboxKeyHandlers,
  enabled: boolean,
) {
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });
  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) =>
      handleInboxKey(event, latest.current);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
