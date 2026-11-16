import { CheckCircleIcon, XCircleIcon } from "@phosphor-icons/react";
import type { RuleResult } from "@/api/types";
import { RuleResultList } from "@/components/RuleResultList";

/**
 * The rule check of a draft: the failed rules (what to fix) or a line that
 * all pass; every rule is behind "Show all rules".
 */
export function DraftRules({ results }: { results: RuleResult[] }) {
  const failed = results.filter((result) => !result.passed);

  return (
    <div className="flex flex-col gap-2">
      {failed.length === 0 ? (
        <p className="flex items-center gap-1.5 text-caption font-medium text-success">
          <CheckCircleIcon className="size-4" aria-hidden />
          All {results.length} campaign rules pass
        </p>
      ) : (
        <>
          <p className="flex items-center gap-1.5 text-caption font-medium text-destructive">
            <XCircleIcon className="size-4" aria-hidden />
            {failed.length} of {results.length} campaign rules fail
          </p>
          <RuleResultList results={failed} />
        </>
      )}
      <details className="text-caption text-muted-foreground">
        <summary className="w-fit cursor-pointer rounded outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
          Show all rules
        </summary>
        <div className="mt-2">
          <RuleResultList results={results} />
        </div>
      </details>
    </div>
  );
}
