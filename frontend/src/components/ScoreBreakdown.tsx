import type { Clip } from "@/api/types";
import { SCORE_PARTS, scoreTone, type ScoreTone } from "@/lib/clips";
import { cn } from "@/lib/utils";

const BAR: Record<ScoreTone, string> = {
  high: "bg-success",
  medium: "bg-warning",
  low: "bg-muted-foreground",
};

/**
 * Why a clip was picked: a bar per score part (Hook, Flow, Value, Trend,
 * colored like the score badge) and the reason text.
 */
export function ScoreBreakdown({ clip }: { clip: Clip }) {
  return (
    <>
      <p className="mb-3 text-body font-medium">Why this clip</p>
      <dl className="flex flex-col gap-2">
        {SCORE_PARTS.map(({ key, label }) => {
          const value = clip.scores[key];
          return (
            <div key={key} className="flex items-center gap-3 text-caption">
              <dt className="w-12 text-muted-foreground">{label}</dt>
              <dd
                role="meter"
                aria-label={label}
                aria-valuemin={0}
                aria-valuemax={99}
                aria-valuenow={value}
                className="flex flex-1 items-center gap-2"
              >
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <span
                    className={cn(
                      "block h-full rounded-full",
                      BAR[scoreTone(value)],
                    )}
                    style={{ width: `${value}%` }}
                  />
                </span>
                <span className="w-6 text-right tabular-nums">{value}</span>
              </dd>
            </div>
          );
        })}
      </dl>
      {clip.reason && (
        <p className="mt-3 text-caption leading-5 text-muted-foreground">
          {clip.reason}
        </p>
      )}
    </>
  );
}
