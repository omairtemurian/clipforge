import { useState } from "react";
import { Field, INPUT } from "./Field";
import { TimeframeSlider } from "./TimeframeSlider";
import { formatDuration } from "@/lib/format";
import { parseTime } from "@/lib/processingSettings";
import { cn } from "@/lib/utils";

interface TimeInputProps {
  label: string;
  value: number;
  /** Called with a typed time; the caller clamps it. */
  onCommit: (seconds: number) => void;
}

/**
 * A time typed as "m:ss" or "h:mm:ss", applied on blur or Enter; text that
 * is not a time goes back to the current value.
 */
function TimeInput({ label, value, onCommit }: TimeInputProps) {
  const [editing, setEditing] = useState<string | null>(null);

  function commit() {
    const seconds = editing === null ? null : parseTime(editing);
    if (seconds !== null) onCommit(seconds);
    setEditing(null);
  }

  return (
    <input
      type="text"
      inputMode="numeric"
      aria-label={label}
      value={editing ?? formatDuration(value)}
      onFocus={() => setEditing(formatDuration(value))}
      onChange={(event) => setEditing(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          commit();
        }
      }}
      className={cn(INPUT, "h-8 w-24 text-center tabular-nums")}
    />
  );
}

interface TimeframeFieldProps {
  duration: number;
  value: [number, number];
  onChange: (value: [number, number]) => void;
}

/** The part of the video to process: a two-handle slider and start/end
 * time inputs, kept at least a second apart inside the video. */
export function TimeframeField({
  duration,
  value,
  onChange,
}: TimeframeFieldProps) {
  const [start, end] = value;
  const clamp = (seconds: number, low: number, high: number) =>
    Math.min(Math.max(Math.round(seconds), low), high);

  return (
    <Field
      label="Timeframe"
      aside={`${formatDuration(start)} – ${formatDuration(end)}`}
    >
      <TimeframeSlider duration={duration} value={value} onChange={onChange} />
      <div className="flex items-center gap-2 text-caption text-muted-foreground">
        <TimeInput
          label="Start time"
          value={start}
          onCommit={(seconds) => onChange([clamp(seconds, 0, end - 1), end])}
        />
        <span aria-hidden>to</span>
        <TimeInput
          label="End time"
          value={end}
          onCommit={(seconds) =>
            onChange([start, clamp(seconds, start + 1, duration)])
          }
        />
      </div>
    </Field>
  );
}
