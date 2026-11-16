import { useWatchStatus } from "@/api/watch";
import { Pill } from "@/components/ui/pill";
import { watchModeLabel, type PushState } from "@/lib/watch";

const DEFAULT_POLL_S = 60;

/** How a channel or streamer is watched, as a small pill: push (green),
 * push pending, or polling. */
export function ModeBadge({ state }: { state: PushState }) {
  const status = useWatchStatus();
  const label = watchModeLabel(
    state,
    status.data?.poll_interval_s ?? DEFAULT_POLL_S,
  );

  return (
    <Pill
      data-state={state}
      tone={state === "subscribed" ? "success" : "neutral"}
      className="shrink-0"
    >
      {label}
    </Pill>
  );
}
