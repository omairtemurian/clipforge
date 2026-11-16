import type { ProEditOptions } from "@/api/types";
import { ColorField } from "@/components/editor/ColorField";
import { NativeSelect } from "@/components/ui/native-select";
import { ToggleRow } from "@/components/ui/toggle-row";
import { BACKGROUND_LABEL, BACKGROUNDS } from "./options";
import type { ProEditForm } from "./useProEditForm";

/** The subject cut-out (SPEC-v3 3.3 motion): the subject in front of the
 * overlays and captions, and the background kept, blurred or swapped for
 * a color. Skipped by the render when the segment engine is missing. */
export function CutoutField({ form }: { form: ProEditForm }) {
  const { background, background_color } = form.options;
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1.5 text-body font-medium">Subject cut-out</legend>
      <ToggleRow
        label="Subject in front of text"
        hint="Overlays and captions go behind the person on screen."
        checked={form.options.subject_front}
        onCheckedChange={form.setSubjectFront}
      />
      <div className="grid grid-cols-[1fr_auto] items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="proedit-background"
            className="text-caption text-muted-foreground"
          >
            Background
          </label>
          <NativeSelect
            id="proedit-background"
            block
            value={background}
            onChange={(event) =>
              form.setBackground(
                event.target.value as ProEditOptions["background"],
              )
            }
          >
            {BACKGROUNDS.map((choice) => (
              <option key={choice} value={choice}>
                {BACKGROUND_LABEL[choice]}
              </option>
            ))}
          </NativeSelect>
        </div>
        {background === "swap" && (
          <ColorField
            label="Background color"
            value={background_color}
            onChange={form.setBackgroundColor}
          />
        )}
      </div>
      <p className="text-caption text-muted-foreground">
        Needs the segment engine (Settings → Engines); without it the edit
        renders without the cut-out.
      </p>
    </fieldset>
  );
}
