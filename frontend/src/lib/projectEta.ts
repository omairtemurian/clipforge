/**
 * The time a job still needs as the card shows it: "ETA …" while it is
 * unknown (null), "ETA <1m" under a minute, "ETA 5m", "ETA 1h 10m".
 */
export function formatEta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "ETA …";
  }
  if (seconds < 60) return "ETA <1m";
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  if (hours === 0) return `ETA ${minutes}m`;
  const rest = minutes % 60;
  return rest === 0 ? `ETA ${hours}h` : `ETA ${hours}h ${rest}m`;
}

/** The text of a progress pill: "48% (ETA 5m)". */
export function progressText(
  percent: number,
  etaSeconds: number | null | undefined,
): string {
  return `${percent}% (${formatEta(etaSeconds)})`;
}
