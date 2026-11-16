import { useState } from "react";
import {
  ArrowClockwiseIcon,
  ClockIcon,
  FilmStripIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { formatDuration } from "@/lib/format";
import type { SourceDetails } from "@/lib/useSourceDetails";
import { Pill } from "@/components/ui/pill";

function Thumbnail({ details }: { details: SourceDetails }) {
  const [broken, setBroken] = useState<string | null>(null);
  const { imageUrl, videoUrl, duration } = details;

  let picture;
  if (videoUrl) {
    picture = (
      <video
        src={`${videoUrl}#t=1`}
        muted
        playsInline
        preload="metadata"
        aria-label="Video preview"
        className="size-full bg-black object-contain"
      />
    );
  } else if (imageUrl && broken !== imageUrl) {
    picture = (
      <img
        src={imageUrl}
        alt=""
        referrerPolicy="no-referrer"
        onError={() => setBroken(imageUrl)}
        className="size-full object-cover"
      />
    );
  } else {
    picture = (
      <div className="flex size-full items-center justify-center text-muted-foreground">
        <FilmStripIcon
          className={details.loading ? "size-8 animate-pulse" : "size-8"}
          aria-hidden
        />
      </div>
    );
  }

  return (
    <div className="relative aspect-video overflow-hidden rounded-xl bg-muted">
      {picture}
      {duration !== null && (
        <Pill tone="overlay" shape="tag" className="absolute right-2 bottom-2">
          {formatDuration(duration)}
        </Pill>
      )}
    </div>
  );
}

/** The chosen video: thumbnail, title, duration, or why it cannot be read. */
export function SourcePreview({ details }: { details: SourceDetails }) {
  return (
    <div className="flex flex-col gap-3">
      <Thumbnail details={details} />
      <p
        className="line-clamp-2 text-body font-medium break-all"
        title={details.title}
      >
        {details.title}
      </p>
      {details.loading ? (
        <p className="flex items-center gap-1.5 text-caption text-muted-foreground">
          <ClockIcon className="size-3.5 animate-pulse" aria-hidden />
          Reading the video…
        </p>
      ) : details.duration !== null ? (
        <p className="flex items-center gap-1.5 text-caption text-muted-foreground">
          <ClockIcon className="size-3.5" aria-hidden />
          {formatDuration(details.duration)}
        </p>
      ) : null}
      {details.error && (
        <div
          role="alert"
          className="flex flex-col items-start gap-2 rounded-lg bg-destructive/10 p-3 text-caption text-destructive"
        >
          <p className="flex min-w-0 gap-1.5">
            <WarningCircleIcon className="size-4 shrink-0" aria-hidden />
            <span className="min-w-0 [overflow-wrap:anywhere]">
              {details.error}
            </span>
          </p>
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={details.retry}
          >
            <ArrowClockwiseIcon aria-hidden />
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}
