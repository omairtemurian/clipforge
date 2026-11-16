import { CheckCircleIcon, XCircleIcon } from "@phosphor-icons/react";
import type { RuleResult } from "@/api/types";
import { RULE_LABEL } from "@/lib/campaignRules";

/** Pass or fail of each campaign rule, with what was found or what to fix. */
export function RuleResultList({ results }: { results: RuleResult[] }) {
  return (
    <ul aria-label="Campaign rules" className="flex flex-col gap-2">
      {results.map((result) => (
        <li
          key={result.rule}
          aria-label={`${RULE_LABEL[result.rule]}: ${result.passed ? "pass" : "fail"}`}
          className="flex gap-2 text-body"
        >
          {result.passed ? (
            <CheckCircleIcon
              className="mt-0.5 size-4 shrink-0 text-success"
              aria-hidden
            />
          ) : (
            <XCircleIcon
              className="mt-0.5 size-4 shrink-0 text-destructive"
              aria-hidden
            />
          )}
          <span className="min-w-0">
            <span className="block font-medium">{RULE_LABEL[result.rule]}</span>
            <span className="block text-caption text-muted-foreground">
              {result.detail}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
