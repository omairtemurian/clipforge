import { ArrowCounterClockwiseIcon } from "@phosphor-icons/react";
import type { CaptionTemplate } from "@/api/types";
import { ColorField } from "@/components/editor/ColorField";
import { Button } from "@/components/ui/button";
import {
  COLOR_PAIRS,
  NO_COLORS,
  hasColors,
  shownColor,
  withColor,
  type CaptionColors,
} from "@/lib/captionColors";

interface CaptionColorsFieldProps {
  /** The chosen caption template; the field waits for it to load. */
  template: CaptionTemplate | undefined;
  value: CaptionColors;
  onChange: (value: CaptionColors) => void;
}

/**
 * The colors of the words and of the spoken word for every clip, over any
 * caption template: two pickers, a few ready-made pairs ("White + green")
 * and a reset to the template's own colors.
 */
export function CaptionColorsField({
  template,
  value,
  onChange,
}: CaptionColorsFieldProps) {
  if (!template) return null;
  return (
    <div className="flex flex-col gap-3" aria-label="Caption colors">
      <div className="grid grid-cols-2 gap-3">
        <ColorField
          label="Text color"
          value={shownColor(template, value, "primary_color")}
          onChange={(color) =>
            onChange(withColor(value, template, "primary_color", color))
          }
        />
        <ColorField
          label="Spoken word color"
          value={shownColor(template, value, "highlight_color")}
          onChange={(color) =>
            onChange(withColor(value, template, "highlight_color", color))
          }
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {COLOR_PAIRS.map((pair) => (
          <Button
            key={pair.label}
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              onChange({
                ...value,
                primary_color: pair.text,
                highlight_color: pair.spoken,
              })
            }
          >
            <span
              aria-hidden
              className="size-2.5 rounded-full"
              style={{ backgroundColor: pair.spoken }}
            />
            {pair.label}
          </Button>
        ))}
        {hasColors(value) && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onChange(NO_COLORS)}
          >
            <ArrowCounterClockwiseIcon aria-hidden />
            Template colors
          </Button>
        )}
      </div>
    </div>
  );
}
