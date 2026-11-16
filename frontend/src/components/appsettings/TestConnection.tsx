import { CheckCircleIcon, PlugIcon, XCircleIcon } from "@phosphor-icons/react";
import { useTestLlm } from "@/api/appSettings";
import type { SettingsView } from "@/api/types";
import { Button } from "@/components/ui/button";
import { llmTestBody, type SettingsDraft } from "@/lib/settingsForm";

interface TestConnectionProps {
  draft: SettingsDraft;
  saved: SettingsView;
}

/** Sends one small request to the model with the values in the form (not
 * saved yet) and shows whether it answered. */
export function TestConnection({ draft, saved }: TestConnectionProps) {
  const test = useTestLlm();
  const result = test.data;
  return (
    <div className="flex flex-col gap-2">
      <div>
        <Button
          type="button"
          variant="outline"
          disabled={test.isPending}
          onClick={() => test.mutate(llmTestBody(draft, saved))}
        >
          <PlugIcon aria-hidden />
          {test.isPending ? "Testing…" : "Test connection"}
        </Button>
      </div>
      {result && !test.isPending && (
        <p
          role="status"
          className={
            result.ok
              ? "flex items-start gap-2 text-body text-success"
              : "flex items-start gap-2 text-body text-destructive"
          }
        >
          {result.ok ? (
            <CheckCircleIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
          ) : (
            <XCircleIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
          )}
          <span className="min-w-0 break-words">
            {result.ok ? "Connected" : "Failed"} ({result.provider},{" "}
            {result.model}): {result.message}
          </span>
        </p>
      )}
    </div>
  );
}
