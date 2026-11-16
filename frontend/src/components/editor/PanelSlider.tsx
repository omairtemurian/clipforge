import { Slider } from "radix-ui";
import { Field } from "@/components/settings/Field";

interface PanelSliderProps {
  label: string;
  /** The value as text, shown right of the label. */
  display: string;
  min: number;
  max: number;
  step: number;
  value: number;
  disabled?: boolean;
  onChange: (value: number) => void;
  /** Called with the value when a drag or key press ends. */
  onCommit?: (value: number) => void;
  /** Called when a drag or key press on the slider starts. */
  onStart?: () => void;
}

/** A labelled slider of a side panel. */
export function PanelSlider({
  label,
  display,
  min,
  max,
  step,
  value,
  disabled,
  onChange,
  onCommit,
  onStart,
}: PanelSliderProps) {
  return (
    <Field label={label} aside={display}>
      <Slider.Root
        min={min}
        max={max}
        step={step}
        value={[value]}
        disabled={disabled}
        onValueChange={([next]) => onChange(next)}
        onValueCommit={onCommit ? ([next]) => onCommit(next) : undefined}
        onPointerDown={onStart}
        onFocus={onStart}
        className="relative flex h-5 w-full touch-none items-center select-none data-[disabled]:opacity-50"
      >
        <Slider.Track className="relative h-1 grow overflow-hidden rounded-full bg-muted">
          <Slider.Range className="absolute h-full bg-primary" />
        </Slider.Track>
        <Slider.Thumb
          aria-label={label}
          className="block size-4 rounded-full bg-foreground shadow outline-none focus-visible:ring-4 focus-visible:ring-ring/40"
        />
      </Slider.Root>
    </Field>
  );
}
