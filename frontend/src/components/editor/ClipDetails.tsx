import { formatTimecode } from "@/lib/format";
import type { ClipRange, CutRange } from "@/lib/timeline";

interface ClipDetailsProps {
  /** The clip's start and end as edited now. */
  range: ClipRange;
  cuts: CutRange[];
  /** The clip's hook text as edited now. */
  hook: string;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border px-3 py-1.5">
      <dt className="text-micro text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

/**
 * Where the edited clip starts and ends on the source, its length after
 * its cuts, how many cuts it has and its hook; they follow every edit.
 */
export function ClipDetails({ range, cuts, hook }: ClipDetailsProps) {
  const cut = cuts.reduce((sum, [from, to]) => sum + (to - from), 0);
  const length = range.end - range.start - cut;

  return (
    <section aria-label="Clip details" className="shrink-0">
      <dl className="grid grid-cols-4 gap-2 text-body">
        <Stat label="In" value={formatTimecode(range.start)} />
        <Stat label="Out" value={formatTimecode(range.end)} />
        <Stat label="Length" value={formatTimecode(length)} />
        <Stat label="Cuts" value={String(cuts.length)} />
      </dl>
      {hook && (
        <p
          className="mt-2 truncate text-caption text-muted-foreground"
          title={hook}
        >
          <span className="font-medium text-foreground">Hook</span> {hook}
        </p>
      )}
    </section>
  );
}
