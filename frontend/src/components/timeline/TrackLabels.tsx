import { LAYER_ROW } from "@/components/timeline/Track";
import { LAYER_LABELS, type LayerName } from "@/lib/layers";
import { cn } from "@/lib/utils";

/** The video and audio rows' heights and gaps (TimelineTracks uses them). */
export const VIDEO_ROW = "mt-1.5 h-12";
export const AUDIO_ROW = "mt-1 h-8";
/** The ruler (h-6), the segment row (h-5) and, when shown, the keyframes
 * row (mt-1 h-3.5) above the tracks. */
const HEADER = "h-11";
const KEYFRAMES = "mt-1 h-3.5";

function Label({ text, row }: { text: string; row: string }) {
  return (
    <div
      className={cn(
        "flex items-center truncate pr-2 text-micro text-muted-foreground",
        row,
      )}
    >
      {text}
    </div>
  );
}

interface TrackLabelsProps {
  /** The layer tracks over the video row and under the audio row. */
  above: LayerName[];
  below: LayerName[];
  /** Whether the keyframes row is shown. */
  keyframes: boolean;
}

/**
 * The timeline's left gutter: each track's name beside its row (the rows'
 * heights are mirrored here, so it stays put while the rows scroll).
 */
export function TrackLabels({ above, below, keyframes }: TrackLabelsProps) {
  return (
    <div aria-hidden className="w-18 shrink-0">
      <div className={HEADER} />
      {keyframes && <div className={KEYFRAMES} />}
      {above.map((name) => (
        <Label key={name} text={LAYER_LABELS[name]} row={LAYER_ROW} />
      ))}
      <Label text="Video" row={VIDEO_ROW} />
      <Label text="Audio" row={AUDIO_ROW} />
      {below.map((name) => (
        <Label key={name} text={LAYER_LABELS[name]} row={LAYER_ROW} />
      ))}
    </div>
  );
}
