/** How much of the chosen video file is on the server (0 to 1). */
export function UploadProgress({ fraction }: { fraction: number }) {
  const percent = Math.floor(fraction * 100);
  return (
    <div className="flex items-center gap-3 text-body text-muted-foreground">
      <div
        role="progressbar"
        aria-label="Upload progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-1.5 w-32 overflow-hidden rounded-full bg-border"
      >
        <div
          className="h-full rounded-full bg-primary transition-[width]"
          style={{ width: `${percent}%` }}
        />
      </div>
      <span aria-live="polite">Uploading {percent}%</span>
    </div>
  );
}
