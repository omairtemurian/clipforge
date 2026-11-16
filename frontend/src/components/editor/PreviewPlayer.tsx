import { PlayIcon } from "@phosphor-icons/react";
import { useState } from "react";
import type { Clip, ProcessingSettings } from "@/api/types";
import { PreviewStatus, type PreviewLoad } from "@/components/PreviewStatus";
import type { PreviewPlayer as Player } from "@/hooks/usePreviewPlayer";
import { previewUrl } from "@/lib/previewUrl";
import { cn } from "@/lib/utils";

type Aspect = ProcessingSettings["aspect"];

/** The CSS aspect-ratio of "W:H" and whether the frame is wider than tall. */
function shape(aspect: Aspect): { ratio: string; wide: boolean } {
  const [width, height] = aspect.split(":").map(Number);
  return { ratio: `${width} / ${height}`, wide: width > height };
}

interface PreviewPlayerProps {
  clip: Clip;
  aspect: Aspect;
  player: Player;
  /** Keep the player (and its time) but do not show it. */
  hidden?: boolean;
}

/**
 * The clip's preview (the 540p proxy render of GET /clips/{id}/preview, as
 * last saved; lib/previewUrl) in a frame of the clip's aspect that fits the
 * column; a click plays or pauses it. The first request renders the
 * preview, so it shows a spinner until the video can play; a preview
 * loaded again after a save starts at the player's time.
 */
export function PreviewPlayer({
  clip,
  aspect,
  player,
  hidden = false,
}: PreviewPlayerProps) {
  const { attach, toggle, playing, events } = player;
  const [status, setStatus] = useState<PreviewLoad>("loading");

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl bg-black",
        shape(aspect).wide ? "max-h-full w-full" : "h-full max-w-full",
        hidden && "hidden",
      )}
      style={{ aspectRatio: shape(aspect).ratio }}
    >
      <video
        ref={attach}
        src={previewUrl(clip)}
        aria-label={`Preview of ${clip.title}`}
        playsInline
        preload="auto"
        onLoadedData={() => {
          if (player.time > 0) player.seek(player.time);
          setStatus("ready");
        }}
        onError={() => setStatus("error")}
        onClick={toggle}
        {...events}
        className="size-full cursor-pointer object-contain"
      />
      <PreviewStatus status={status} />
      {status === "ready" && !playing && (
        <button
          type="button"
          aria-label="Play preview"
          onClick={toggle}
          className="absolute top-1/2 left-1/2 flex size-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-background/70 text-foreground backdrop-blur-sm transition-colors outline-none hover:bg-background/90 focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <PlayIcon weight="fill" className="ml-0.5 size-6" aria-hidden />
        </button>
      )}
    </div>
  );
}
