import { useState } from "react";
import { BellIcon, BellSlashIcon } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { useWatchEvents } from "@/api/watch";
import { Button } from "@/components/ui/button";
import { projectPath } from "@/components/navigation";
import {
  desktopAlertsAllowed,
  desktopAlertsSupported,
  requestDesktopAlerts,
} from "@/lib/desktopAlerts";
import { formatDate } from "@/lib/format";
import { alertText } from "@/lib/watch";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * The latest alerts, newest first: what was detected, how long after it
 * was published (or went live), and the project it became. The button asks
 * the browser for desktop alerts.
 */
export function RecentAlerts() {
  const events = useWatchEvents();
  const [allowed, setAllowed] = useState(desktopAlertsAllowed);

  return (
    <section aria-labelledby="watch-alerts" className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <h2 id="watch-alerts" className="text-section">
          Recent alerts
        </h2>
        {desktopAlertsSupported() &&
          (allowed ? (
            <span className="text-caption text-muted-foreground">
              Desktop alerts on
            </span>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={async () => setAllowed(await requestDesktopAlerts())}
            >
              <BellIcon aria-hidden />
              Enable desktop alerts
            </Button>
          ))}
      </div>
      {events.isSuccess && events.data.length === 0 && (
        <EmptyState icon={BellSlashIcon} title="No alerts yet" className="py-8">
          New uploads and go-lives show up here and as a notification on any
          page.
        </EmptyState>
      )}
      {events.data && events.data.length > 0 && (
        <ul
          aria-label="Recent alerts"
          className={cn(cardClass(), "flex flex-col divide-y divide-border")}
        >
          {events.data.map((event) => {
            const { title, body } = alertText(event);
            return (
              <li
                key={event.id}
                className="flex items-center justify-between gap-4 px-5 py-3 text-body"
              >
                <div className="min-w-0">
                  <p className="font-medium">{title}</p>
                  <p className="truncate text-muted-foreground">{body}</p>
                </div>
                <div className="flex shrink-0 items-center gap-3 text-caption text-muted-foreground">
                  <span>
                    {formatDate(event.detected_at)} · {event.via}
                  </span>
                  {event.project_id !== null ? (
                    <Link
                      className="font-medium text-primary-ink hover:underline"
                      to={projectPath(event.project_id)}
                    >
                      Open project
                    </Link>
                  ) : (
                    event.url && (
                      <a
                        className="font-medium text-primary-ink hover:underline"
                        href={event.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open
                      </a>
                    )
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
