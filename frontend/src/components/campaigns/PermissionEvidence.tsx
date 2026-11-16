import { ShieldCheckIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { apiUrl } from "@/api/client";
import type { Campaign } from "@/api/types";
import { FileField } from "@/components/brand/FileField";
import { formatDate } from "@/lib/format";
import { TextField } from "./TextField";

interface PermissionEvidenceProps {
  /** The saved campaign, absent for a new one. */
  campaign?: Campaign;
  url: string;
  screenshot: File | null;
  urlError?: string;
  screenshotError?: string;
  /** Changes whenever the saved screenshot may have changed. */
  version: number;
  onUrlChange: (url: string) => void;
  onScreenshotPick: (file: File | null) => void;
}

/**
 * The evidence that the owner may clip the creator: the page that shows it,
 * a screenshot of it and the date they were saved. Publishing for the
 * campaign stays blocked until all three are there.
 */
export function PermissionEvidence({
  campaign,
  url,
  screenshot,
  urlError,
  screenshotError,
  version,
  onUrlChange,
  onScreenshotPick,
}: PermissionEvidenceProps) {
  const complete = campaign?.permission_complete === true;
  const hasScreenshot = campaign?.permission_screenshot_asset_id != null;
  return (
    <fieldset className="flex flex-col gap-4 rounded-xl border border-border p-4">
      <legend className="px-1 text-body font-medium">
        Permission evidence
      </legend>
      <p
        role="status"
        className={
          complete
            ? "flex items-center gap-2 text-body text-success"
            : "flex items-center gap-2 text-body text-warning"
        }
      >
        {complete ? (
          <ShieldCheckIcon className="size-4" aria-hidden />
        ) : (
          <WarningCircleIcon className="size-4" aria-hidden />
        )}
        {complete && campaign?.permission_checked_at
          ? `Complete, saved ${formatDate(campaign.permission_checked_at)}. Publishing is allowed.`
          : "Incomplete: publishing is blocked until the link, the screenshot and the date are saved."}
      </p>
      <TextField
        label="Permission source link"
        type="url"
        value={url}
        onChange={onUrlChange}
        error={urlError}
        placeholder="https://… (the page that says you may clip this creator)"
      />
      <FileField
        label="Permission screenshot"
        accept="image/png,image/jpeg,image/webp"
        file={screenshot}
        savedName={hasScreenshot ? "Saved screenshot" : null}
        error={screenshotError}
        onPick={onScreenshotPick}
      />
      {campaign && hasScreenshot && screenshot === null && (
        <a
          href={apiUrl(
            `/campaigns/${campaign.id}/permission-screenshot?v=${version}`,
          )}
          target="_blank"
          rel="noreferrer"
          className="text-caption text-primary-ink underline-offset-4 hover:underline"
        >
          Open the saved screenshot
        </a>
      )}
    </fieldset>
  );
}
