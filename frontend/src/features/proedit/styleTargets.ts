import type { StyleMetric, StyleTarget, StyleTargets } from "@/api/types";

export const GROUP_LABEL: Record<StyleMetric["group"], string> = {
  rhythm: "Rhythm",
  motion: "Motion",
  look: "Look",
  effects: "Effects",
  captions: "Captions",
  audio: "Audio",
  structure: "Structure",
};

/** The metric groups in the order they appear, each with its metrics. */
export function groupMetrics(
  metrics: StyleMetric[],
): [StyleMetric["group"], StyleMetric[]][] {
  const groups = new Map<StyleMetric["group"], StyleMetric[]>();
  for (const metric of metrics) {
    groups.set(metric.group, [...(groups.get(metric.group) ?? []), metric]);
  }
  return [...groups];
}

/** Round value to the decimals of step (4 at most), so slider values do
 * not carry float noise. */
export function snap(value: number, step: number): number {
  const decimals = Math.min(4, (String(step).split(".")[1] ?? "").length);
  return Number(value.toFixed(decimals));
}

/** The bounds of metric's slider, widened to hold target's range: the
 * references may measure values outside the usual bounds. */
export function sliderBounds(
  metric: StyleMetric,
  target: StyleTarget | undefined,
): { min: number; max: number } {
  return {
    min: Math.min(metric.min, target?.low ?? metric.min),
    max: Math.max(metric.max, target?.high ?? metric.max),
  };
}

/** A value with its unit, e.g. "42/min", "30%" (a share), "140 BPM". */
export function formatValue(
  value: number,
  metric: Pick<StyleMetric, "unit" | "step">,
): string {
  if (metric.unit === "share") return `${Math.round(value * 100)}%`;
  const shown = snap(value, metric.step).toString();
  if (!metric.unit) return shown;
  if (metric.unit.startsWith("/")) return `${shown}${metric.unit}`;
  return `${shown} ${metric.unit}`;
}

/** Targets with metric's target moved to value: the range moves with it
 * (keeping its width on each side) inside the slider's bounds. */
export function moveTarget(
  targets: StyleTargets,
  metric: StyleMetric,
  value: number,
): StyleTargets {
  const target = targets.metrics[metric.key];
  if (!target) return targets;
  const bounds = sliderBounds(metric, target);
  const below = target.median - target.low;
  const above = target.high - target.median;
  const moved: StyleTarget = {
    ...target,
    median: value,
    low: snap(Math.max(bounds.min, value - below), metric.step),
    high: snap(Math.min(bounds.max, value + above), metric.step),
  };
  return { ...targets, metrics: { ...targets.metrics, [metric.key]: moved } };
}

/** Targets with a hand-set target for metric: the middle of its slider
 * with its tolerance on each side (no reference measured it). */
export function addTarget(
  targets: StyleTargets,
  metric: StyleMetric,
): StyleTargets {
  const median = snap((metric.min + metric.max) / 2, metric.step);
  const target: StyleTarget = {
    median,
    low: snap(Math.max(metric.min, median - metric.tolerance), metric.step),
    high: snap(Math.min(metric.max, median + metric.tolerance), metric.step),
    count: 0,
  };
  return { ...targets, metrics: { ...targets.metrics, [metric.key]: target } };
}

/** Targets without metric's target: the style-match ignores it. */
export function removeTarget(
  targets: StyleTargets,
  metric: StyleMetric,
): StyleTargets {
  const metrics = { ...targets.metrics };
  delete metrics[metric.key];
  return { ...targets, metrics };
}
