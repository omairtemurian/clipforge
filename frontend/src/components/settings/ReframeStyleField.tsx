import { useReframePresets } from "@/api/reframe";
import type { ProcessingSettings } from "@/api/types";
import { Field } from "./Field";
import { NativeSelect } from "@/components/ui/native-select";

/** The "Reframe style" select of the settings panel: how reframe frames
 * the clips of a kind of video (podcast, stand-up, gaming, vlog); the
 * default picks the layout from what the video shows. Picking a style
 * also sets its camera motion (Automatic: calm). */
export function ReframeStyleField({
  settings,
  onChange,
}: {
  settings: ProcessingSettings;
  onChange: (patch: Partial<ProcessingSettings>) => void;
}) {
  const presets = useReframePresets().data ?? [];
  const chosen = presets.find(
    (preset) => preset.name === settings.reframe_preset,
  );

  return (
    <Field label="Reframe style" htmlFor="settings-reframe-style">
      <NativeSelect
        id="settings-reframe-style"
        value={settings.reframe_preset ?? ""}
        onChange={(event) => {
          const name = event.target.value || null;
          const preset = presets.find((item) => item.name === name);
          onChange({
            reframe_preset: name as ProcessingSettings["reframe_preset"],
            camera_motion: preset?.camera_motion ?? "calm",
          });
        }}
        block
      >
        <option value="">Automatic</option>
        {presets.map((preset) => (
          <option key={preset.name} value={preset.name}>
            {preset.label}
          </option>
        ))}
      </NativeSelect>
      {chosen && (
        <p className="text-caption text-muted-foreground">
          {chosen.description}
        </p>
      )}
    </Field>
  );
}
