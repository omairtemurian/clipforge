import { useId, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FloppyDiskIcon } from "@phosphor-icons/react";
import { useSaveAppSettings } from "@/api/appSettings";
import type { KindUsage, SettingsView } from "@/api/types";
import { usageKey, useUsage } from "@/api/usage";
import { Button } from "@/components/ui/button";
import { INPUT } from "@/components/settings/Field";
import {
  CAP_ROWS,
  capDraftOf,
  capPatch,
  formatUsed,
  parseCap,
  type CapDraft,
  type CapRow,
} from "@/lib/usageCaps";
import { cn } from "@/lib/utils";
import { Section } from "./Section";

function CapLine({
  row,
  used,
  value,
  onChange,
}: {
  row: CapRow;
  used: KindUsage | undefined;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  const invalid = parseCap(value) === null;
  return (
    <li className="grid grid-cols-[1fr_auto_9rem] items-center gap-4 py-3 text-body">
      <label htmlFor={id} className="font-medium">
        {row.label} cap
        <span className="block text-caption font-normal text-muted-foreground">
          {row.unit} per month
        </span>
      </label>
      <span className="text-right tabular-nums">
        <span className="text-muted-foreground">This month: </span>
        {used ? formatUsed(row.kind, used.units) : "…"}
        {used?.exceeded && (
          <span role="status" className="ml-2 text-destructive">
            Cap reached
          </span>
        )}
      </span>
      <input
        id={id}
        inputMode="decimal"
        value={value}
        placeholder="No cap"
        aria-invalid={invalid}
        onChange={(event) => onChange(event.target.value)}
        className={cn(INPUT, "h-9 text-right tabular-nums")}
      />
    </li>
  );
}

/** What the jobs used this month (compute time, LLM tokens, paid API calls)
 * and the optional monthly caps that stop new jobs. The caps are settings,
 * saved with their own button. */
export function UsageSection({ saved }: { saved: SettingsView }) {
  const queryClient = useQueryClient();
  const usage = useUsage();
  const [draft, setDraft] = useState<CapDraft>(() => capDraftOf(saved));
  const save = useSaveAppSettings((next) => {
    setDraft(capDraftOf(next));
    void queryClient.invalidateQueries({ queryKey: usageKey });
  });
  const patch = capPatch(draft, saved);
  const dirty = patch !== null && Object.keys(patch).length > 0;
  const kinds = new Map(usage.data?.kinds.map((item) => [item.kind, item]));

  return (
    <Section
      title="Usage"
      description="What your jobs used this month. A cap stops new jobs once it is reached; leave it empty for no cap."
    >
      {usage.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the usage.
        </p>
      )}
      <ul className="flex flex-col divide-y divide-border">
        {CAP_ROWS.map((row) => (
          <CapLine
            key={row.field}
            row={row}
            used={kinds.get(row.kind)}
            value={draft[row.field]}
            onChange={(value) =>
              setDraft((current) => ({ ...current, [row.field]: value }))
            }
          />
        ))}
      </ul>
      {patch === null && (
        <p role="alert" className="text-caption text-destructive">
          A cap must be a number of 0 or more.
        </p>
      )}
      <div>
        <Button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() => patch && save.mutate(patch)}
        >
          <FloppyDiskIcon aria-hidden />
          {save.isPending ? "Saving…" : "Save caps"}
        </Button>
      </div>
    </Section>
  );
}
