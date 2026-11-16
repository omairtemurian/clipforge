import { CheckCircleIcon } from "@phosphor-icons/react";
import type { PlatformStatus } from "@/api/types";
import { platformLabel } from "@/lib/platforms";
import { NeedsKeys } from "./NeedsKeys";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** The state of each platform's developer app: ready, or the env vars
 * that are missing. */
export function DeveloperApps({ platforms }: { platforms: PlatformStatus[] }) {
  if (platforms.length === 0) return null;
  return (
    <section aria-labelledby="developer-apps" className="flex flex-col gap-4">
      <h2 id="developer-apps" className="text-section">
        Developer apps
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2">
        {platforms.map((status) => (
          <li
            key={status.platform}
            aria-label={`${platformLabel(status.platform)} developer app`}
            className={cn(cardClass(), "flex flex-col gap-2 p-4")}
          >
            <p className="font-medium">{platformLabel(status.platform)}</p>
            {status.configured ? (
              <p className="flex items-center gap-1.5 text-caption text-muted-foreground">
                <CheckCircleIcon
                  aria-hidden
                  className="size-3.5 text-primary-ink"
                />
                Developer app keys are set
              </p>
            ) : (
              <NeedsKeys status={status} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
