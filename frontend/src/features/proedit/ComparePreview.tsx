import { PauseIcon, PlayIcon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { Clip } from "@/api/types";
import { PreviewStatus, type PreviewLoad } from "@/components/PreviewStatus";
import { Button } from "@/components/ui/button";
import { formatTimecode } from "@/lib/format";
import { previewUrl } from "@/lib/previewUrl";
import { MEDIA_FRAME } from "@/lib/surfaces";
import { variantVideoUrl } from "./paths";
import { useSyncedPair } from "./useSyncedPair";
import { VariantProgress } from "./VariantProgress";

/** A seek asked of the previews: to t seconds; n tells two seeks to the
 * same time apart. */
export interface SeekRequest {
  t: number;
  n: number;
}

export interface ComparePreviewProps {
  original: Clip;
  variant: Clip;
  /** Changes whenever the variant's video was rendered again (its URL's
   * version); null: none is rendered. */
  videoVersion: string | null;
  seek: SeekRequest;
  /** The playhead, shown under the previews. */
  time: number;
  /** The time of the leading preview (the Pro Edit's, or the original's
   * while the Pro Edit has no video). */
  onTime: (t: number) => void;
}

/** Why the Pro Edit side has no video: rendering (with its progress),
 * failed, or not rendered yet. */
function NoVideo({ variant }: { variant: Clip }) {
  const text =
    variant.status === "rendering"
      ? "Rendering the Pro Edit…"
      : variant.status === "failed"
        ? "The Pro Edit render failed."
        : "The Pro Edit is not rendered yet.";
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-4 text-center text-body text-muted-foreground">
      <p>{text}</p>
      <VariantProgress clip={variant} />
    </div>
  );
}

function Side({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <figcaption className="text-micro font-medium text-muted-foreground uppercase">
        {title}
      </figcaption>
      <div className={`${MEDIA_FRAME} aspect-[9/16] h-[42vh] max-w-full`}>
        {children}
      </div>
    </figure>
  );
}

const VIDEO = "absolute inset-0 size-full object-contain";

/**
 * The original and the Pro Edit side by side (SPEC-v3 3.8), played,
 * paused and sought together (useSyncedPair); the original is muted so
 * only the Pro Edit's sound plays. The original's preview is rendered on
 * its first request, so it shows a spinner until it can play.
 */
export function ComparePreview({
  original,
  variant,
  videoVersion,
  seek,
  time,
  onTime,
}: ComparePreviewProps) {
  const pair = useSyncedPair(videoVersion !== null, onTime);
  const { left, right, playing } = pair;
  const originalSrc = previewUrl(original);
  const [loaded, setLoaded] = useState<{ src: string; load: PreviewLoad }>();
  const originalLoad = loaded?.src === originalSrc ? loaded.load : "loading";

  useEffect(() => {
    for (const ref of [left, right]) {
      if (ref.current) ref.current.currentTime = seek.t;
    }
  }, [seek, left, right]);

  return (
    <section aria-label="Side-by-side preview" className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-4">
        <Side title="Original">
          <video
            ref={left}
            src={originalSrc}
            aria-label="Original preview"
            muted
            playsInline
            preload="auto"
            {...pair.events("left")}
            onLoadedData={() => {
              setLoaded({ src: originalSrc, load: "ready" });
              pair.follow();
            }}
            onError={() => setLoaded({ src: originalSrc, load: "error" })}
            className={VIDEO}
          />
          <PreviewStatus status={originalLoad} />
        </Side>
        <Side title="Pro Edit">
          {videoVersion === null ? (
            <NoVideo variant={variant} />
          ) : (
            <video
              ref={right}
              src={variantVideoUrl(variant.id, videoVersion)}
              aria-label="Pro Edit preview"
              playsInline
              preload="metadata"
              {...pair.events("right")}
              className={VIDEO}
            />
          )}
        </Side>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={pair.toggle}>
          {playing ? <PauseIcon aria-hidden /> : <PlayIcon aria-hidden />}
          {playing ? "Pause" : "Play both"}
        </Button>
        <span className="text-body text-muted-foreground tabular-nums">
          {formatTimecode(time)}
        </span>
      </div>
    </section>
  );
}
