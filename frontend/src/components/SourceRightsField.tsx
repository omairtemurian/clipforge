import { useId } from "react";
import { Field, INPUT } from "@/components/settings/Field";
import {
  CREDIT_LINE_MAX,
  RIGHTS_OPTIONS,
  type SourceRights,
} from "@/lib/sourceRights";
import { cn } from "@/lib/utils";
import { NativeSelect } from "@/components/ui/native-select";

interface SourceRightsFieldProps {
  /** "" until the owner chooses. */
  rights: SourceRights | "";
  creditLine: string;
  onRightsChange: (rights: SourceRights | "") => void;
  onCreditLineChange: (creditLine: string) => void;
}

/**
 * The copyright guard (SPEC-v2 1.6): a required "Source rights" select and
 * the credit line shown with the clips.
 */
export function SourceRightsField({
  rights,
  creditLine,
  onRightsChange,
  onCreditLineChange,
}: SourceRightsFieldProps) {
  const id = useId();
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-5">
      <Field label="Source rights" htmlFor={`${id}-rights`}>
        <NativeSelect
          id={`${id}-rights`}
          required
          value={rights}
          onChange={(event) =>
            onRightsChange(event.target.value as SourceRights | "")
          }
          block
        >
          <option value="" disabled>
            Choose why you may use this video
          </option>
          {RIGHTS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field label="Credit line" htmlFor={`${id}-credit`}>
        <input
          id={`${id}-credit`}
          type="text"
          maxLength={CREDIT_LINE_MAX}
          value={creditLine}
          onChange={(event) => onCreditLineChange(event.target.value)}
          placeholder="Optional: e.g. Video by Ann, CC BY"
          className={cn(INPUT, "h-9")}
        />
      </Field>
    </div>
  );
}
