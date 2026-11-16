import { useId } from "react";
import { Field, INPUT } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";
import { cn } from "@/lib/utils";

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  /** A textarea with this many rows instead of a one-line input. */
  rows?: number;
  type?: "text" | "number" | "date" | "url";
  placeholder?: string;
  maxLength?: number;
  hint?: string;
}

/** A labelled text input or textarea with its error under it. */
export function TextField({
  label,
  value,
  onChange,
  error,
  rows,
  type = "text",
  placeholder,
  maxLength,
  hint,
}: TextFieldProps) {
  const id = useId();
  const shared = {
    id,
    value,
    placeholder,
    maxLength,
    "aria-invalid": error !== undefined,
    onChange: (
      event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    ) => onChange(event.target.value),
  };
  return (
    <Field label={label} htmlFor={id}>
      {rows ? (
        <textarea
          {...shared}
          rows={rows}
          className={cn(INPUT, "resize-y py-2")}
        />
      ) : (
        <input
          {...shared}
          type={type}
          step={type === "number" ? "any" : undefined}
          className={cn(INPUT, "h-9")}
        />
      )}
      {hint && !error && (
        <p className="text-caption text-muted-foreground">{hint}</p>
      )}
      {error && (
        <p role="alert" className="text-caption text-destructive">
          {error}
        </p>
      )}
    </Field>
  );
}

interface SelectFieldProps<T extends string> {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}

/** A labelled native select. */
export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: SelectFieldProps<T>) {
  const id = useId();
  return (
    <Field label={label} htmlFor={id}>
      <NativeSelect
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
        block
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </NativeSelect>
    </Field>
  );
}
