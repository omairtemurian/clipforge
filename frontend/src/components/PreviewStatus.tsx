import { CircleNotchIcon } from "@phosphor-icons/react";

/** How far a preview video (GET /clips/{id}/preview) has loaded. */
export type PreviewLoad = "loading" | "ready" | "error";

/**
 * The overlay of a preview video while it is not ready: the backend renders
 * a preview on its first request, so a spinner shows until the video can
 * play, and an alert if it could not be made. Nothing once it is ready.
 */
export function PreviewStatus({ status }: { status: PreviewLoad }) {
  if (status === "loading") {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-body text-muted-foreground">
        <CircleNotchIcon className="size-6 animate-spin" aria-hidden />
        Making the preview…
      </div>
    );
  }
  if (status === "error") {
    return (
      <p
        role="alert"
        className="absolute inset-0 flex items-center justify-center p-6 text-center text-body text-muted-foreground"
      >
        The preview could not be made. Check the backend log.
      </p>
    );
  }
  return null;
}
