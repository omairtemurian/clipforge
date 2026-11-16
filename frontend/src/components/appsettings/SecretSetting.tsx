import { useId } from "react";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import type { KeyDraft } from "@/lib/settingsForm";
import { cn } from "@/lib/utils";

interface SecretSettingProps {
  label: string;
  /** Whether the server has a key saved; its value is never sent. */
  isSet: boolean;
  draft: KeyDraft;
  onChange: (draft: KeyDraft) => void;
}

/**
 * A write-only field for an API key: it shows only whether a key is saved,
 * never the key. Typing replaces it; "Remove key" clears it on Save.
 */
export function SecretSetting({
  label,
  isSet,
  draft,
  onChange,
}: SecretSettingProps) {
  const id = useId();
  const removing = isSet && draft.clear && !draft.typed;
  const status = removing
    ? "Will be removed when you save"
    : isSet
      ? "Saved"
      : "Not set";
  return (
    <Field label={label} htmlFor={id} aside={status}>
      <div className="flex gap-2">
        <input
          id={id}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={draft.typed}
          placeholder={
            isSet ? "Leave blank to keep the saved key" : "Paste key"
          }
          onChange={(event) =>
            onChange({ typed: event.target.value, clear: false })
          }
          className={cn(INPUT, "h-9")}
        />
        {isSet && (
          <Button
            type="button"
            variant="outline"
            size="lg"
            aria-pressed={removing}
            onClick={() => onChange({ typed: "", clear: !draft.clear })}
          >
            {removing ? "Keep key" : "Remove key"}
          </Button>
        )}
      </div>
    </Field>
  );
}
