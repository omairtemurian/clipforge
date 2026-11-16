import { BroadcastIcon } from "@phosphor-icons/react";
import { useWatchStatus } from "@/api/watch";
import { watchStatusLine } from "@/lib/watch";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** The top line of the Watchlist: whether new items arrive by push or by
 * polling (and how often). */
export function WatchStatusBanner() {
  const status = useWatchStatus();
  if (!status.data) return null;

  return (
    <p
      role="status"
      className={cn(
        cardClass(),
        "flex items-start gap-2 px-4 py-3 text-body text-muted-foreground",
      )}
    >
      <BroadcastIcon
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-primary-ink"
      />
      {watchStatusLine(status.data)}
    </p>
  );
}
