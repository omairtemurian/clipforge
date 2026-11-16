import type { StyleMetric, StyleTargets } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  addTarget,
  formatValue,
  GROUP_LABEL,
  groupMetrics,
  moveTarget,
  removeTarget,
  sliderBounds,
} from "./styleTargets";

/** One metric's row: the slider of its target (the median of the
 * references) with its range, or a button that sets a target by hand. */
function TargetRow({
  metric,
  targets,
  disabled,
  onChange,
}: {
  metric: StyleMetric;
  targets: StyleTargets;
  disabled: boolean;
  onChange: (targets: StyleTargets) => void;
}) {
  const target = targets.metrics[metric.key];
  const id = `style-target-${metric.key}`;
  if (!target) {
    return (
      <li className="flex items-center justify-between gap-3 text-body">
        <span className="text-muted-foreground">{metric.label}: no target</span>
        <Button
          size="xs"
          variant="ghost"
          disabled={disabled}
          aria-label={`Set a ${metric.label} target`}
          onClick={() => onChange(addTarget(targets, metric))}
        >
          Set
        </Button>
      </li>
    );
  }
  const bounds = sliderBounds(metric, target);
  const shown = formatValue(target.median, metric);
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-3 text-body">
        <label htmlFor={id} className="font-medium">
          {metric.label}
        </label>
        <span className="flex items-center gap-2">
          <span className="tabular-nums">{shown}</span>
          <Button
            size="xs"
            variant="ghost"
            disabled={disabled}
            aria-label={`Clear the ${metric.label} target`}
            onClick={() => onChange(removeTarget(targets, metric))}
          >
            Clear
          </Button>
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={bounds.min}
        max={bounds.max}
        step={metric.step}
        value={target.median}
        aria-valuetext={shown}
        disabled={disabled}
        onChange={(event) =>
          onChange(moveTarget(targets, metric, Number(event.target.value)))
        }
        className="w-full accent-primary"
      />
      <span className="text-caption text-muted-foreground">
        Range {formatValue(target.low, metric)} to{" "}
        {formatValue(target.high, metric)}
        {target.count > 0
          ? ` · from ${target.count} reference${target.count === 1 ? "" : "s"}`
          : " · set by hand"}
      </span>
    </li>
  );
}

/**
 * The targets of a recipe as sliders, by group (SPEC-v3 4.4): each
 * slider moves a metric's target and its range with it; a metric without
 * a target is ignored by the style-match until one is set. The caption
 * color is a color picker.
 */
export function RecipeTargets({
  metrics,
  targets,
  disabled,
  onChange,
}: {
  metrics: StyleMetric[];
  targets: StyleTargets;
  disabled: boolean;
  onChange: (targets: StyleTargets) => void;
}) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {groupMetrics(metrics).map(([group, members]) => (
        <section
          key={group}
          aria-label={GROUP_LABEL[group]}
          className="flex flex-col gap-3"
        >
          <h3 className="text-body font-semibold">{GROUP_LABEL[group]}</h3>
          <ul className="flex flex-col gap-3">
            {members.map((metric) => (
              <TargetRow
                key={metric.key}
                metric={metric}
                targets={targets}
                disabled={disabled}
                onChange={onChange}
              />
            ))}
          </ul>
          {group === "captions" && (
            <label className="flex items-center justify-between gap-3 text-body font-medium">
              Caption color
              <input
                type="color"
                value={targets.caption_color ?? "#ffffff"}
                disabled={disabled}
                onChange={(event) =>
                  onChange({ ...targets, caption_color: event.target.value })
                }
                className="h-8 w-12 cursor-pointer rounded border border-border bg-card"
              />
            </label>
          )}
        </section>
      ))}
    </div>
  );
}
