import type { CaptionTemplate } from "@/api/types";
import { CaptionFontField } from "@/components/editor/CaptionFontField";
import { ColorField } from "@/components/editor/ColorField";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { ChoiceChips } from "@/components/settings/ChoiceChips";
import { Field } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";
import { ToggleRow } from "@/components/ui/toggle-row";
import type { NO_STYLE, StyleField } from "@/lib/clipLook";

const POSITIONS = [
  { value: "top", label: "Top" },
  { value: "middle", label: "Middle" },
  { value: "lower_third", label: "Lower third" },
  { value: "bottom", label: "Bottom" },
] as const;

const COLORS = [
  { field: "primary_color", label: "Text" },
  { field: "highlight_color", label: "Spoken word" },
  { field: "emphasis_color", label: "Emphasis" },
] as const;

const LINES = [
  { value: "1", label: "1 line" },
  { value: "2", label: "2 lines" },
] as const;

const ANIMATIONS: { value: CaptionTemplate["animation"]; label: string }[] = [
  { value: "none", label: "None" },
  { value: "pop", label: "Pop" },
  { value: "bounce", label: "Bounce" },
  { value: "fade", label: "Fade in" },
  { value: "reveal", label: "Reveal word by word" },
  { value: "shake", label: "Shake" },
  { value: "underline", label: "Underline" },
  { value: "pill", label: "Pill" },
  { value: "hollow", label: "Hollow" },
];

const SIZE_MIN = 20;
const SIZE_MAX = 200;
const STROKE_MAX = 20;

export type SetStyle = <F extends StyleField>(
  field: F,
  value: NonNullable<(typeof NO_STYLE)[F]>,
  dragged?: boolean,
) => void;

interface CaptionStyleFieldsProps {
  /** The template's fields with the clip's style applied. */
  shown: CaptionTemplate;
  setStyle: SetStyle;
  /** Called when a slider or color picker is first used (one undo step). */
  onStart: () => void;
}

/**
 * The fields of a caption style that replace the template's: font, size,
 * colors, stroke, shadow, box, position, lines, words per line, animation,
 * uppercase and emoji.
 */
export function CaptionStyleFields({
  shown,
  setStyle,
  onStart,
}: CaptionStyleFieldsProps) {
  return (
    <>
      <CaptionFontField
        value={shown.font}
        onChange={(font) => setStyle("font", font)}
      />
      <PanelSlider
        label="Size"
        display={`${shown.size} px`}
        min={SIZE_MIN}
        max={SIZE_MAX}
        step={2}
        value={shown.size}
        onChange={(size) => setStyle("size", size, true)}
        onStart={onStart}
      />
      <div className="grid grid-cols-3 gap-2">
        {COLORS.map(({ field, label }) => (
          <ColorField
            key={field}
            label={label}
            value={shown[field]}
            onChange={(color) => setStyle(field, color, true)}
            onStart={onStart}
          />
        ))}
      </div>
      <div className="grid grid-cols-[1fr_5.5rem] items-end gap-3">
        <PanelSlider
          label="Stroke"
          display={`${shown.outline} px`}
          min={0}
          max={STROKE_MAX}
          step={0.5}
          value={shown.outline}
          onChange={(outline) => setStyle("outline", outline, true)}
          onStart={onStart}
        />
        <ColorField
          label="Stroke color"
          value={shown.outline_color}
          onChange={(color) => setStyle("outline_color", color, true)}
          onStart={onStart}
        />
      </div>
      <PanelSlider
        label="Shadow"
        display={`${shown.shadow} px`}
        min={0}
        max={STROKE_MAX}
        step={0.5}
        value={shown.shadow}
        onChange={(shadow) => setStyle("shadow", shadow, true)}
        onStart={onStart}
      />
      <ToggleRow
        label="Box"
        hint="Draw a box behind the words, in the stroke color"
        checked={shown.box}
        onCheckedChange={(on) => setStyle("box", on)}
      />
      <Field label="Position">
        <ChoiceChips
          label="Caption position"
          options={[...POSITIONS]}
          value={shown.position}
          onChange={(position) => setStyle("position", position)}
        />
      </Field>
      <Field label="Lines">
        <ChoiceChips
          label="Caption lines"
          options={[...LINES]}
          value={String(shown.max_lines) as "1" | "2"}
          onChange={(lines) => setStyle("max_lines", Number(lines))}
        />
      </Field>
      <PanelSlider
        label="Words per line"
        display={String(shown.max_words_per_line)}
        min={1}
        max={6}
        step={1}
        value={shown.max_words_per_line}
        onChange={(words) => setStyle("max_words_per_line", words, true)}
        onStart={onStart}
      />
      <Field label="Animation">
        <NativeSelect
          block
          aria-label="Caption animation"
          value={shown.animation}
          onChange={(event) =>
            setStyle(
              "animation",
              event.target.value as CaptionTemplate["animation"],
            )
          }
        >
          {ANIMATIONS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <ToggleRow
        label="Uppercase"
        hint="Show the words in capitals"
        checked={shown.uppercase}
        onCheckedChange={(on) => setStyle("uppercase", on)}
      />
      <ToggleRow
        label="Emoji"
        hint="Add an emoji after keywords"
        checked={shown.emoji}
        onCheckedChange={(on) => setStyle("emoji", on)}
      />
    </>
  );
}
