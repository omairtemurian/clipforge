import { ArrowsClockwiseIcon } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import type { StyleMatch, StyleMetricMatch } from "@/api/types";
import { Button } from "@/components/ui/button";
import { styleRecipesPath } from "./paths";
import { useMeasureStyleMatch, useStyleMatch } from "./styleApi";
import { formatValue } from "./styleTargets";

const DETAIL_STEP = 0.01;

/** How one metric of the video fits its target. */
function MetricRow({ metric }: { metric: StyleMetricMatch }) {
  const format = (value: number) =>
    formatValue(value, { unit: metric.unit, step: DETAIL_STEP });
  return (
    <li className="text-body">
      <div className="flex items-center justify-between gap-3">
        <span>{metric.label}</span>
        <span className="tabular-nums">{Math.round(metric.score * 100)}%</span>
      </div>
      <span className="text-caption text-muted-foreground">
        {format(metric.value)} · target {format(metric.target.median)} (
        {format(metric.target.low)} to {format(metric.target.high)})
      </span>
    </li>
  );
}

/** The score of a measured style-match and its metrics, worst first. */
function MatchResult({ match }: { match: StyleMatch }) {
  const metrics = [...match.metrics].sort((a, b) => a.score - b.score);
  return (
    <>
      <p className="text-body">
        <span className="text-section tabular-nums">
          {match.score ?? "—"}/100
        </span>{" "}
        <span className="text-muted-foreground">
          against{" "}
          <Link
            to={styleRecipesPath(match.recipe_id)}
            className="text-primary-ink underline-offset-4 hover:underline"
          >
            {match.recipe_name}
          </Link>
        </span>
      </p>
      {match.score === null && (
        <p className="text-body text-muted-foreground">
          The recipe has no target this video could be measured on.
        </p>
      )}
      <ul aria-label="Style metrics" className="flex flex-col gap-1.5">
        {metrics.map((metric) => (
          <MetricRow key={metric.key} metric={metric} />
        ))}
      </ul>
    </>
  );
}

/**
 * The style-match of a rendered Pro Edit variant (SPEC-v3 4.4): how close
 * its video is to the targets of its plan's style recipe, as a 0-100 score
 * with the fit of each metric. It is measured on demand (the video is
 * analyzed like a reference) and kept until the video changes.
 */
export function StyleMatchPanel({ variantId }: { variantId: number }) {
  const match = useStyleMatch(variantId);
  const measure = useMeasureStyleMatch(variantId);
  return (
    <section aria-label="Style match" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-body font-semibold">Style match</h3>
        <Button
          size="sm"
          variant="outline"
          disabled={measure.isPending}
          onClick={() => measure.mutate()}
        >
          <ArrowsClockwiseIcon aria-hidden />
          {measure.isPending ? "Measuring…" : "Measure"}
        </Button>
      </div>
      {match.data ? (
        <MatchResult match={match.data} />
      ) : (
        <p className="text-body text-muted-foreground">
          Measure the rendered video to see how close it is to its style recipe.
        </p>
      )}
    </section>
  );
}
