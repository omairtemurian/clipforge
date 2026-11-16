import { Slider } from "radix-ui";
import { formatDuration } from "@/lib/format";

interface TimeframeSliderProps {
  duration: number;
  value: [number, number];
  onChange: (value: [number, number]) => void;
}

const THUMB =
  "block size-4 rounded-full border-2 border-primary bg-background shadow outline-none focus-visible:ring-4 focus-visible:ring-ring/40";

/** A two-handle slider over the video: the part to look for clips in. */
export function TimeframeSlider({
  duration,
  value,
  onChange,
}: TimeframeSliderProps) {
  const [start, end] = value;
  return (
    <div className="flex flex-col gap-2">
      <Slider.Root
        min={0}
        max={duration}
        step={1}
        minStepsBetweenThumbs={1}
        value={value}
        onValueChange={(next) => onChange([next[0], next[1]])}
        aria-label="Timeframe"
        className="relative flex h-5 w-full touch-none items-center select-none"
      >
        <Slider.Track className="relative h-1.5 grow overflow-hidden rounded-full bg-muted">
          <Slider.Range className="absolute h-full bg-primary" />
        </Slider.Track>
        <Slider.Thumb
          aria-label="Timeframe start"
          aria-valuetext={formatDuration(start)}
          className={THUMB}
        />
        <Slider.Thumb
          aria-label="Timeframe end"
          aria-valuetext={formatDuration(end)}
          className={THUMB}
        />
      </Slider.Root>
      <div className="flex justify-between text-caption text-muted-foreground tabular-nums">
        <span>{formatDuration(0)}</span>
        <span>{formatDuration(duration)}</span>
      </div>
    </div>
  );
}
