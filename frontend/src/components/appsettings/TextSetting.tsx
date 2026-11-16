import { useId } from "react";
import { Field, INPUT } from "@/components/settings/Field";
import { cn } from "@/lib/utils";

interface TextSettingProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  placeholder?: string;
  /** Suggestions shown under the input (a datalist); any text is allowed. */
  options?: string[];
}

/** A labelled one-line input of the Settings page, with a hint and an error. */
export function TextSetting({
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
  options,
}: TextSettingProps) {
  const id = useId();
  return (
    <Field label={label} htmlFor={id}>
      <input
        id={id}
        value={value}
        placeholder={placeholder}
        list={options ? `${id}-options` : undefined}
        aria-invalid={error !== undefined}
        aria-describedby={hint ? `${id}-hint` : undefined}
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
        className={cn(INPUT, "h-9")}
      />
      {options && (
        <datalist id={`${id}-options`}>
          {options.map((option) => (
            <option key={option} value={option} />
          ))}
        </datalist>
      )}
      {hint && (
        <p id={`${id}-hint`} className="text-caption text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p role="alert" className="text-caption text-destructive">
          {error}
        </p>
      )}
    </Field>
  );
}
