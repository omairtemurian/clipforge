import type { Project } from "@/api/types";

const HAS_ZONE = /(Z|[+-]\d\d:?\d\d)$/;

/** A timestamp of the API as a Date; the API sends UTC without a zone. */
export function parseApiDate(iso: string): Date {
  return new Date(HAS_ZONE.test(iso) ? iso : `${iso}Z`);
}

/** A date as "2026.10.30" (local time); the API sends UTC without a zone. */
export function formatDate(iso: string): string {
  const date = parseApiDate(iso);
  if (Number.isNaN(date.getTime())) return "";
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}.${month}.${day}`;
}

/** How long ago an API timestamp was: "just now", "5 min ago", "3 h ago"
 * or, from a day on, its date; "" if it is not a date. */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const minutes = Math.floor(
    (now.getTime() - parseApiDate(iso).getTime()) / 60_000,
  );
  if (Number.isNaN(minutes)) return "";
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ago`;
  return formatDate(iso);
}

/** "1 clip" / "3 clips". */
export function clipCountLabel(count: number): string {
  return `${count} ${count === 1 ? "clip" : "clips"}`;
}

/**
 * The name of a project: its title, or while ingest has not found one the
 * link or the file name it was made from.
 */
export function projectName(project: Project): string {
  if (project.title) return project.title;
  if (project.source_url) return project.source_url;
  return project.source_path.split(/[\\/]/).pop() || "Untitled video";
}

/** A length in seconds as "mm:ss", or "h:mm:ss" from one hour on. */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const secs = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${minutes}:${secs}` : `${minutes}:${secs}`;
}

/** A time in seconds as "mm:ss.cc" (hundredths), as the editor shows it. */
export function formatTimecode(seconds: number): string {
  const hundredths = Math.max(0, Math.round(seconds * 100));
  const minutes = String(Math.floor(hundredths / 6000)).padStart(2, "0");
  const secs = String(Math.floor((hundredths % 6000) / 100)).padStart(2, "0");
  const rest = String(hundredths % 100).padStart(2, "0");
  return `${minutes}:${secs}.${rest}`;
}

const BYTE_UNITS = ["KB", "MB", "GB", "TB"];

/** A size in bytes in decimal units: "0 B", "512 B", "1.5 MB", "12 GB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${Math.max(0, Math.round(bytes))} B`;
  let value = bytes;
  let unit = -1;
  while (value >= 1000 && unit < BYTE_UNITS.length - 1) {
    value /= 1000;
    unit += 1;
  }
  const digits = value < 10 ? 1 : 0;
  return `${Number(value.toFixed(digits))} ${BYTE_UNITS[unit]}`;
}
