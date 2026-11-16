import { ArrowsClockwiseIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useClip } from "@/api/clips";
import type { Clip, EdlItem, ProEditRun } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ComparePreview, type SeekRequest } from "./ComparePreview";
import { EdlLanes } from "./EdlLanes";
import { PlanTools } from "./PlanTools";
import { useJobEvents } from "@/hooks/useJobEvents";
import {
  usePatchPlan,
  useProEditPlan,
  useProEditTiming,
  useReloadVariant,
} from "./planApi";
import { useProEditRuns, useRenderVariants } from "./runApi";

const ACTIVE: ProEditRun["status"][] = ["queued", "running"];

/** The variant of variants that ?variant= names, else the newest. */
function chosenVariant(variants: Clip[], param: string | null): Clip {
  const id = Number(param);
  return variants.find((v) => v.id === id) ?? variants[variants.length - 1];
}

/** Links to each variant's editor when the clip has more than one. */
function VariantPicker({
  variants,
  current,
}: {
  variants: Clip[];
  current: number;
}) {
  if (variants.length < 2) return null;
  return (
    <nav aria-label="Pro Edit variants" className="flex flex-wrap gap-2">
      {variants.map((variant, index) => (
        <Link
          key={variant.id}
          to={`?variant=${variant.id}`}
          aria-current={variant.id === current ? "page" : undefined}
          className={cn(
            "rounded-full border px-3 py-1 text-body",
            variant.id === current
              ? "border-primary bg-primary/10"
              : "border-border hover:border-foreground/25",
          )}
        >
          Variant {index + 1}
        </Link>
      ))}
    </nav>
  );
}

/**
 * The editor of one Pro Edit variant: the side-by-side preview and the EDL
 * lanes of its current plan. An edit is stored at once as the plan's next
 * version (PATCH, shown as it was dropped until the server answers; a
 * refused edit snaps back with the server's reasons); while the newest plan
 * is not the rendered one it offers to render it. Nothing is editable
 * while a job of the variant runs; everything loads again when it ends.
 */
function VariantEditor({
  original,
  variantId,
}: {
  original: Clip;
  variantId: number;
}) {
  const variant = useClip(variantId);
  const plan = useProEditPlan(variantId);
  const timing = useProEditTiming(variantId);
  const runs = useProEditRuns(variantId);
  const patch = usePatchPlan(variantId);
  const render = useRenderVariants();
  const active = (runs.data ?? []).find((run) => ACTIVE.includes(run.status));
  useJobEvents(active?.job_id ?? undefined, useReloadVariant(variantId));
  const [pending, setPending] = useState<EdlItem[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [seek, setSeek] = useState<SeekRequest>({ t: 0, n: 0 });

  if (variant.isPending || plan.isPending || timing.isPending) {
    return <Skeleton className="h-96 rounded-xl" />;
  }
  if (variant.isError || timing.isError) {
    return (
      <p role="alert" className="text-body text-destructive">
        Could not load this Pro Edit variant.
      </p>
    );
  }
  const clip = variant.data;
  const busy = clip.status === "rendering" || active !== undefined;
  const rendered = (runs.data ?? []).find((run) => run.status === "done");
  const videoVersion =
    clip.status === "rendered"
      ? (rendered?.finished_at ?? clip.output_path)
      : null;
  const items = pending ?? plan.data?.items ?? [];
  const commit = (next: EdlItem[]) => {
    setPending(next);
    patch.mutate(next, { onSettled: () => setPending(null) });
  };
  const apply = (edited: EdlItem) =>
    commit(items.map((item) => (item.id === edited.id ? edited : item)));
  const toTime = (t: number) => {
    setPlayhead(t);
    setSeek((last) => ({ t, n: last.n + 1 }));
  };

  return (
    <div className="flex flex-col gap-6">
      <ComparePreview
        original={original}
        variant={clip}
        videoVersion={videoVersion}
        seek={seek}
        time={playhead}
        onTime={setPlayhead}
      />
      {plan.isError ? (
        <p className="text-body text-muted-foreground">
          {busy
            ? "The Pro Edit is still making its plan."
            : "This variant has no plan yet."}
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p aria-label="Plan version" className="text-body">
              Plan v{plan.data.version}
              {patch.isPending && (
                <span className="text-muted-foreground"> · saving…</span>
              )}
              {busy && (
                <span className="text-muted-foreground">
                  {" "}
                  · a job is running
                </span>
              )}
            </p>
            {!busy && rendered && rendered.plan_id !== plan.data.id && (
              <Button
                size="sm"
                onClick={() => render.mutate([variantId])}
                disabled={render.isPending}
              >
                <ArrowsClockwiseIcon aria-hidden />
                Render plan v{plan.data.version}
              </Button>
            )}
          </div>
          {patch.isError && (
            <p role="alert" className="text-body text-destructive">
              {patch.error.message}
            </p>
          )}
          <EdlLanes
            items={items}
            timing={timing.data}
            playhead={playhead}
            selectedId={selectedId}
            onSelect={setSelectedId}
            disabled={busy || patch.isPending}
            onCommit={commit}
            onSeek={toTime}
          />
          <PlanTools
            variantId={variantId}
            plan={plan.data}
            runs={runs.data ?? []}
            selected={items.find((item) => item.id === selectedId)}
            busy={busy || patch.isPending}
            onApply={apply}
          />
        </>
      )}
    </div>
  );
}

/**
 * The Pro Edit editor of original (SPEC-v3 3.8): its variants to pick
 * from (?variant=, default the newest) and the chosen one's editor.
 */
export function ProEditEditor({
  original,
  variants,
}: {
  original: Clip;
  variants: Clip[];
}) {
  const [params] = useSearchParams();
  const variant = chosenVariant(variants, params.get("variant"));
  return (
    <div className="flex flex-col gap-4">
      <VariantPicker variants={variants} current={variant.id} />
      <VariantEditor
        key={variant.id}
        original={original}
        variantId={variant.id}
      />
    </div>
  );
}
