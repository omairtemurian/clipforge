import { ArrowCounterClockwiseIcon } from "@phosphor-icons/react";
import { ColorField } from "@/components/editor/ColorField";
import { Button } from "@/components/ui/button";

interface SpeakerColorsProps {
  /** The diarized speakers of the clip's words. */
  speakers: string[];
  /** The clip's speaker colors (caption_style.speaker_colors). */
  colors: Record<string, string> | null;
  /** The color of a speaker without a color of their own. */
  baseColor: string;
  onChange: (colors: Record<string, string> | null, dragged?: boolean) => void;
  onStart: () => void;
}

/**
 * A color for the words of each speaker of the clip (the spoken word and
 * emphasis words keep their template colors), and a reset to the
 * template's colors.
 */
export function SpeakerColors({
  speakers,
  colors,
  baseColor,
  onChange,
  onStart,
}: SpeakerColorsProps) {
  if (speakers.length === 0) {
    return (
      <p className="text-body text-muted-foreground">
        No speakers were told apart in this clip.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-2">
        {speakers.map((speaker, index) => (
          <ColorField
            key={speaker}
            label={`Speaker ${index + 1}`}
            value={colors?.[speaker] ?? baseColor}
            onChange={(color) =>
              onChange({ ...colors, [speaker]: color }, true)
            }
            onStart={onStart}
          />
        ))}
      </div>
      {colors && Object.keys(colors).length > 0 && (
        <Button type="button" variant="outline" onClick={() => onChange(null)}>
          <ArrowCounterClockwiseIcon aria-hidden />
          Same color for every speaker
        </Button>
      )}
    </div>
  );
}
