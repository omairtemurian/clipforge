import type { ProcessingSettings } from "@/api/types";
import { ToggleRow } from "@/components/ui/toggle-row";
import { ChoiceChips } from "./ChoiceChips";

export type ZoomOutIntensity = ProcessingSettings["zoom_out_moments"];

const INTENSITIES: { value: ZoomOutIntensity; label: string }[] = [
  { value: "subtle", label: "Subtle" },
  { value: "balanced", label: "Balanced" },
  { value: "frequent", label: "Frequent" },
];

/** The intensity that switching the toggle on picks. */
const DEFAULT_ON: ZoomOutIntensity = "balanced";

interface ZoomOutMomentsProps {
  value: ZoomOutIntensity;
  onChange: (value: ZoomOutIntensity) => void;
  disabled?: boolean;
  /** The line under the toggle's label (default: what the moments are). */
  hint?: string;
}

/**
 * The "Zoom-out moments" control: a switch (off: auto clips stay cropped to
 * fill) and, while it is on, how often a clip zooms out to show a square
 * or the whole frame (subtle, balanced or frequent).
 */
export function ZoomOutMoments({
  value,
  onChange,
  disabled,
  hint = "Zoom out to a square or the whole frame for wide shots and lost subjects",
}: ZoomOutMomentsProps) {
  const on = value !== "off";
  return (
    <div className="flex flex-col gap-2">
      <ToggleRow
        label="Zoom-out moments"
        hint={hint}
        checked={on}
        disabled={disabled}
        onCheckedChange={(next) => onChange(next ? DEFAULT_ON : "off")}
      />
      {on && (
        <ChoiceChips
          label="Zoom-out intensity"
          options={INTENSITIES}
          value={value}
          onChange={onChange}
          disabled={disabled}
        />
      )}
    </div>
  );
}
