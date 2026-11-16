import { useEffect, useRef } from "react";
import type { FilmstripData } from "@/api/timelineAssets";
import type { ClipRange } from "@/lib/timeline";
import { filmstripSlots } from "@/lib/timelineMedia";

interface TimelineFilmstripProps {
  strip: FilmstripData;
  view: ClipRange;
  /** The drawn size of the row in px. */
  width: number;
  height: number;
}

/** The video row's pictures: filmstrip tiles side by side across the view,
 * each the source frame at its place. The image's object URL lives in the
 * --strip property while the strip is shown. */
export function TimelineFilmstrip({
  strip,
  view,
  width,
  height,
}: TimelineFilmstripProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const url = URL.createObjectURL(strip.image);
    ref.current?.style.setProperty("--strip", `url(${url})`);
    return () => URL.revokeObjectURL(url);
  }, [strip.image]);

  const tile = height * strip.tileAspect;
  return (
    <div
      ref={ref}
      aria-hidden
      data-testid="filmstrip"
      className="absolute inset-0 overflow-hidden"
    >
      {filmstripSlots(strip, view, width, height).map(({ left, index }) => (
        <div
          key={left}
          className="absolute inset-y-0 bg-no-repeat"
          style={{
            left,
            width: tile,
            backgroundImage: "var(--strip)",
            backgroundSize: `${strip.count * tile}px ${height}px`,
            backgroundPosition: `${-index * tile}px 0`,
          }}
        />
      ))}
    </div>
  );
}
