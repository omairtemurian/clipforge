import { ListDashesIcon } from "@phosphor-icons/react";
import { useState } from "react";
import type { CaptionCensor as Censor } from "@/api/types";
import { CensorListDialog } from "@/components/editor/CensorListDialog";
import { ChoiceChips } from "@/components/settings/ChoiceChips";
import { Field } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { ToggleRow } from "@/components/ui/toggle-row";

const MODES = [
  { value: "beep", label: "Beep" },
  { value: "mute", label: "Mute" },
] as const;

interface CaptionCensorProps {
  /** The clip's censor (null: only the words marked "Censor", beeped). */
  value: Censor | null;
  onChange: (censor: Censor) => void;
}

/**
 * Censoring of swear words: "Auto censor" censors the words of the built-in
 * and custom lists, a word's popover censors one word; a censored word's
 * caption is masked ("f***") and its sound beeped or muted. "Censor list"
 * edits the custom list.
 */
export function CaptionCensor({ value, onChange }: CaptionCensorProps) {
  const [listOpen, setListOpen] = useState(false);
  const censor = value ?? { auto: false, mode: "beep" };
  return (
    <>
      <ToggleRow
        label="Auto censor"
        hint="Mask and bleep swear words from the lists"
        checked={censor.auto}
        onCheckedChange={(auto) => onChange({ ...censor, auto })}
      />
      <Field label="Sound of a censored word">
        <ChoiceChips
          label="Censor sound"
          options={[...MODES]}
          value={censor.mode}
          onChange={(mode) => onChange({ ...censor, mode })}
        />
      </Field>
      <Button type="button" variant="outline" onClick={() => setListOpen(true)}>
        <ListDashesIcon aria-hidden />
        Censor list
      </Button>
      {listOpen && <CensorListDialog onClose={() => setListOpen(false)} />}
    </>
  );
}
