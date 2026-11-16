import type { TextProps } from "@/api/types";
import { CaptionFontField } from "@/components/editor/CaptionFontField";
import { ColorField } from "@/components/editor/ColorField";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { Field } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";
import { ToggleRow } from "@/components/ui/toggle-row";
import { TEXT_ANIMATIONS, type TextAnimation } from "@/lib/overlays";

/** A change of a text layer's props; dragged: part of a slider or color
 * drag (one undo step). */
export type SetTextProps = (
  changes: Partial<TextProps>,
  dragged?: boolean,
) => void;

interface TextLayerFieldsProps {
  props: TextProps;
  onChange: SetTextProps;
  /** Called when a slider or color picker is first used. */
  onStart: () => void;
}

const percent = (value: number) => `${Math.round(value * 100)}%`;
const seconds = (value: number) => `${value.toFixed(1)} s`;

interface AnimationFieldProps {
  label: string;
  value: TextAnimation;
  length: number;
  onChange: (value: TextAnimation) => void;
  onLength: (value: number) => void;
  onStart: () => void;
}

/** How a text layer comes in or goes out, and over how long. */
function AnimationField(props: AnimationFieldProps) {
  return (
    <>
      <Field label={props.label}>
        <NativeSelect
          block
          aria-label={props.label}
          value={props.value}
          onChange={(event) =>
            props.onChange(event.target.value as TextAnimation)
          }
        >
          {TEXT_ANIMATIONS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </Field>
      {props.value !== "none" && (
        <PanelSlider
          label={`${props.label} length`}
          display={seconds(props.length)}
          min={0.1}
          max={3}
          step={0.1}
          value={props.length}
          onChange={props.onLength}
          onStart={props.onStart}
        />
      )}
    </>
  );
}

/**
 * The look of a text layer: font, size, color, an optional outline and
 * background box, where it sits in the frame and how it comes in and goes
 * out (TextProps; the render draws it as pipeline/text_overlay does).
 */
export function TextLayerFields({
  props,
  onChange,
  onStart,
}: TextLayerFieldsProps) {
  const drag = (changes: Partial<TextProps>) => onChange(changes, true);
  return (
    <div className="flex flex-col gap-5">
      <CaptionFontField
        ariaLabel="Text font"
        value={props.font}
        onChange={(font) => onChange({ font })}
      />
      <PanelSlider
        label="Size"
        display={percent(props.size)}
        min={0.02}
        max={0.3}
        step={0.005}
        value={props.size}
        onChange={(size) => drag({ size })}
        onStart={onStart}
      />
      <ColorField
        label="Text color"
        value={props.color}
        onChange={(color) => drag({ color })}
        onStart={onStart}
      />
      <ToggleRow
        label="Outline"
        checked={props.stroke !== null}
        onCheckedChange={(on) => onChange({ stroke: on ? "#000000" : null })}
      />
      {props.stroke !== null && (
        <div className="grid grid-cols-2 gap-3">
          <ColorField
            label="Outline color"
            value={props.stroke}
            onChange={(stroke) => drag({ stroke })}
            onStart={onStart}
          />
          <PanelSlider
            label="Outline width"
            display={percent(props.stroke_width)}
            min={0.01}
            max={0.3}
            step={0.01}
            value={props.stroke_width}
            onChange={(stroke_width) => drag({ stroke_width })}
            onStart={onStart}
          />
        </div>
      )}
      <ToggleRow
        label="Background box"
        checked={props.box !== null}
        onCheckedChange={(on) => onChange({ box: on ? "#000000" : null })}
      />
      {props.box !== null && (
        <div className="grid grid-cols-2 gap-3">
          <ColorField
            label="Box color"
            value={props.box}
            onChange={(box) => drag({ box })}
            onStart={onStart}
          />
          <PanelSlider
            label="Box opacity"
            display={percent(props.box_opacity)}
            min={0}
            max={1}
            step={0.05}
            value={props.box_opacity}
            onChange={(box_opacity) => drag({ box_opacity })}
            onStart={onStart}
          />
        </div>
      )}
      <PanelSlider
        label="Left to right"
        display={percent(props.x)}
        min={0}
        max={1}
        step={0.01}
        value={props.x}
        onChange={(x) => drag({ x })}
        onStart={onStart}
      />
      <PanelSlider
        label="Top to bottom"
        display={percent(props.y)}
        min={0}
        max={1}
        step={0.01}
        value={props.y}
        onChange={(y) => drag({ y })}
        onStart={onStart}
      />
      <AnimationField
        label="Animation in"
        value={props.animation_in}
        length={props.in_seconds}
        onChange={(animation_in) => onChange({ animation_in })}
        onLength={(in_seconds) => drag({ in_seconds })}
        onStart={onStart}
      />
      <AnimationField
        label="Animation out"
        value={props.animation_out}
        length={props.out_seconds}
        onChange={(animation_out) => onChange({ animation_out })}
        onLength={(out_seconds) => drag({ out_seconds })}
        onStart={onStart}
      />
    </div>
  );
}
