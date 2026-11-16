import { useId } from "react";
import { Field } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";
import type { VideoEncoder } from "@/lib/settingsForm";
import { Section } from "./Section";

const ENCODERS: { value: VideoEncoder; label: string }[] = [
  { value: "h264_videotoolbox", label: "Hardware (VideoToolbox)" },
  { value: "libx264", label: "Software (x264)" },
];

interface RenderSectionProps {
  value: VideoEncoder;
  /** The encoders that this machine's ffmpeg has. */
  available: VideoEncoder[];
  onChange: (encoder: VideoEncoder) => void;
}

/** How clips are encoded: the H.264 encoder of renders and previews. */
export function RenderSection({
  value,
  available,
  onChange,
}: RenderSectionProps) {
  const id = useId();
  return (
    <Section
      title="Rendering"
      description="How clips are encoded to H.264 video."
    >
      <Field label="Video encoder" htmlFor={id}>
        <NativeSelect
          id={id}
          value={value}
          aria-describedby={`${id}-hint`}
          onChange={(event) => onChange(event.target.value as VideoEncoder)}
          block
        >
          {ENCODERS.filter(
            (encoder) =>
              available.includes(encoder.value) || encoder.value === value,
          ).map((encoder) => (
            <option key={encoder.value} value={encoder.value}>
              {encoder.label}
            </option>
          ))}
        </NativeSelect>
        <p id={`${id}-hint`} className="text-caption text-muted-foreground">
          Hardware encoding renders about 3-4 times faster on a Mac at the same
          quality; software encoding makes files about a quarter smaller.
        </p>
      </Field>
    </Section>
  );
}
