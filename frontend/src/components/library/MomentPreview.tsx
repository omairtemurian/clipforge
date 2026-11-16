import { useEffect, useRef } from "react";
import { apiUrl } from "@/api/client";
import type { SearchHit } from "@/api/types";
import { formatDuration } from "@/lib/format";

/**
 * The source video of the moment being played, started at the moment.
 * A new moment of the same video seeks instead of reloading it.
 */
export function MomentPreview({ hit }: { hit: SearchHit | null }) {
  const video = useRef<HTMLVideoElement>(null);
  const src = hit ? apiUrl(`/media/${hit.project_id}/source`) : undefined;

  useEffect(() => {
    const element = video.current;
    if (!element || !hit) return;
    const seek = () => {
      element.currentTime = hit.start;
      void Promise.resolve(element.play()).catch(() => undefined);
    };
    if (element.readyState >= 1) seek();
    else element.addEventListener("loadedmetadata", seek, { once: true });
    return () => element.removeEventListener("loadedmetadata", seek);
  }, [hit]);

  if (!hit) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-xl border border-dashed border-border p-6 text-center text-body text-muted-foreground">
        Play a moment to watch it here.
      </div>
    );
  }
  return (
    <figure>
      <video
        ref={video}
        src={src}
        controls
        preload="metadata"
        aria-label={`Source video of ${hit.project_title}`}
        className="aspect-video w-full rounded-xl bg-black"
      />
      <figcaption className="mt-2 text-caption text-muted-foreground">
        {hit.project_title} · from {formatDuration(hit.start)}
      </figcaption>
    </figure>
  );
}
