import type { ProcessingSettings } from "@/api/types";
import { ChoiceChips } from "./ChoiceChips";

export type CameraMotion = ProcessingSettings["camera_motion"];

const MOTIONS: { value: CameraMotion; label: string; hint: string }[] = [
  {
    value: "calm",
    label: "Calm",
    hint: "Rests on the subject and glides to it in slow, smooth moves",
  },
  {
    value: "normal",
    label: "Normal",
    hint: "Smooth moves that react a little sooner",
  },
  {
    value: "fast",
    label: "Fast",
    hint: "Follows the subject closely, for sports and gameplay",
  },
];

interface CameraMotionFieldProps {
  value: CameraMotion;
  onChange: (value: CameraMotion) => void;
  disabled?: boolean;
}

/**
 * The "Camera motion" control: how the auto-tracking window moves (calm,
 * normal or fast), with a line on what the chosen motion does.
 */
export function CameraMotionField({
  value,
  onChange,
  disabled,
}: CameraMotionFieldProps) {
  const chosen = MOTIONS.find((motion) => motion.value === value);
  return (
    <div className="flex flex-col gap-2">
      <span className="text-body font-medium">Camera motion</span>
      <ChoiceChips
        label="Camera motion"
        options={MOTIONS}
        value={value}
        onChange={onChange}
        disabled={disabled}
      />
      <p className="text-caption text-muted-foreground">{chosen?.hint}</p>
    </div>
  );
}
