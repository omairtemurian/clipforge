import type { ProcessingSettings } from "@/api/types";
import { SCENE_LABELS } from "@/lib/scenes";
import { Field } from "./Field";
import { NativeSelect } from "@/components/ui/native-select";

type DefaultLayout = ProcessingSettings["default_layout"];

const OPTIONS: { value: DefaultLayout; label: string; hint: string }[] = [
  {
    value: "auto",
    label: "Automatic",
    hint: "Each clip gets the layout that fits what it shows.",
  },
  {
    value: "dynamic",
    label: "Switch per segment",
    hint: "Clips switch layout at scene cuts and when the number of speakers changes.",
  },
  {
    value: "fill",
    label: "Fill",
    hint: "Every clip crops the video to fill the frame.",
  },
  ...(["fit", "split", "grid", "pip", "screenshare", "gameplay"] as const).map(
    (value) => ({
      value,
      label: SCENE_LABELS[value],
      hint: `Every clip starts in the ${SCENE_LABELS[value].toLowerCase()} layout.`,
    }),
  ),
];

/** The "Default layout" select of the settings panel: the layout that new
 * clips get (each one's own, one per segment, or one for all of them). */
export function DefaultLayoutField({
  settings,
  onChange,
}: {
  settings: ProcessingSettings;
  onChange: (patch: Partial<ProcessingSettings>) => void;
}) {
  const chosen = OPTIONS.find(
    (option) => option.value === settings.default_layout,
  );

  return (
    <Field label="Default layout" htmlFor="settings-default-layout">
      <NativeSelect
        id="settings-default-layout"
        value={settings.default_layout}
        onChange={(event) =>
          onChange({ default_layout: event.target.value as DefaultLayout })
        }
        block
      >
        {OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </NativeSelect>
      {chosen && (
        <p className="text-caption text-muted-foreground">{chosen.hint}</p>
      )}
    </Field>
  );
}
