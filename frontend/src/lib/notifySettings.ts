import type { SettingsUpdate, SettingsView } from "@/api/types";
import type { KeyDraft } from "@/lib/settingsForm";

export type NotifyTextField =
  "smtp_host" | "smtp_user" | "smtp_from" | "notify_email_to";

export interface NotifyDraft {
  text: Record<NotifyTextField, string>;
  /** Typed as text so that a half-typed number is not lost. */
  smtp_port: string;
  quota_warn_percent: string;
  /** "HH:MM", or empty for no daily digest. */
  digest_time: string;
  desktop_notifications: boolean;
  smtp_password: KeyDraft;
}

export const NOTIFY_TEXT_FIELDS: NotifyTextField[] = [
  "smtp_host",
  "smtp_user",
  "smtp_from",
  "notify_email_to",
];

/** The draft that shows the saved notification settings, no password typed. */
export function notifyDraftOf(view: SettingsView): NotifyDraft {
  return {
    text: Object.fromEntries(
      NOTIFY_TEXT_FIELDS.map((field) => [field, view[field]]),
    ) as Record<NotifyTextField, string>,
    smtp_port: String(view.smtp_port),
    quota_warn_percent: String(view.quota_warn_percent),
    digest_time: view.digest_time,
    desktop_notifications: view.desktop_notifications,
    smtp_password: { typed: "", clear: false },
  };
}

/** A whole port from 1 to 65535, or null. */
export function parsePort(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const port = Number(trimmed);
  return port >= 1 && port <= 65535 ? port : null;
}

/** A percent above 0 and below 100, or null. */
export function parseWarnPercent(text: string): number | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) && value > 0 && value < 100 ? value : null;
}

/** Whether text is empty (no digest) or a time of day, "HH:MM" on 24 hours. */
export function isDigestTime(text: string): boolean {
  return /^(([01]\d|2[0-3]):[0-5]\d)?$/.test(text.trim());
}

/** The problems of a draft by field name. */
export function notifyProblems(draft: NotifyDraft): Record<string, string> {
  const problems: Record<string, string> = {};
  if (parsePort(draft.smtp_port) === null) {
    problems.smtp_port = "Enter a port from 1 to 65535.";
  }
  if (parseWarnPercent(draft.quota_warn_percent) === null) {
    problems.quota_warn_percent = "Enter a percent above 0 and below 100.";
  }
  if (!isDigestTime(draft.digest_time)) {
    problems.digest_time = "Enter a time like 08:00, or leave it blank.";
  }
  return problems;
}

/** The settings that differ from the saved ones, as a PUT body; the
 * password is sent when typed, or as "" when removed. Invalid numbers and times are
 * left out (see notifyProblems). */
export function notifyPatch(
  draft: NotifyDraft,
  saved: SettingsView,
): SettingsUpdate {
  const patch: SettingsUpdate = {};
  for (const field of NOTIFY_TEXT_FIELDS) {
    const value = draft.text[field].trim();
    if (value !== saved[field]) patch[field] = value;
  }
  const port = parsePort(draft.smtp_port);
  if (port !== null && port !== saved.smtp_port) patch.smtp_port = port;
  const percent = parseWarnPercent(draft.quota_warn_percent);
  if (percent !== null && percent !== saved.quota_warn_percent) {
    patch.quota_warn_percent = percent;
  }
  const digest = draft.digest_time.trim();
  if (isDigestTime(digest) && digest !== saved.digest_time) {
    patch.digest_time = digest;
  }
  if (draft.desktop_notifications !== saved.desktop_notifications) {
    patch.desktop_notifications = draft.desktop_notifications;
  }
  const { typed, clear } = draft.smtp_password;
  if (typed.trim()) patch.smtp_password = typed.trim();
  else if (clear) patch.smtp_password = "";
  return patch;
}

/** Whether the draft differs from the saved settings, also by a number that
 * is not valid yet (so Save can show what is wrong with it). */
export function notifyDirty(draft: NotifyDraft, saved: SettingsView): boolean {
  return (
    Object.keys(notifyPatch(draft, saved)).length > 0 ||
    draft.smtp_port.trim() !== String(saved.smtp_port) ||
    draft.quota_warn_percent.trim() !== String(saved.quota_warn_percent) ||
    draft.digest_time.trim() !== saved.digest_time
  );
}
