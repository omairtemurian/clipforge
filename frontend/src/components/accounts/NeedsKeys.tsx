import { KeyIcon } from "@phosphor-icons/react";
import { publishingSetupUrl } from "@/api/accounts";
import type { PlatformStatus } from "@/api/types";
import { missingKeysLine } from "@/lib/platforms";

/** What a platform's developer app still needs: shown instead of a
 * connect button while its keys are missing. */
export function NeedsKeys({ status }: { status: PlatformStatus }) {
  return (
    <div className="space-y-1 text-caption text-muted-foreground">
      <p className="flex items-center gap-1.5 font-medium text-foreground">
        <KeyIcon aria-hidden className="size-3.5 text-primary-ink" />
        Needs developer app keys
      </p>
      <p>
        {missingKeysLine(status)}{" "}
        <a
          href={publishingSetupUrl(status.platform)}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-foreground"
        >
          See setup
        </a>
      </p>
    </div>
  );
}
