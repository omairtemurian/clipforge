import type { ReactNode } from "react";

interface FieldProps {
  label: string;
  /** The id of the control the label names (omit for groups). */
  htmlFor?: string;
  /** Shown right of the label, e.g. the current value. */
  aside?: ReactNode;
  children: ReactNode;
}

/** A labelled row of the settings panel. */
export function Field({ label, htmlFor, aside, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        {htmlFor ? (
          <label htmlFor={htmlFor} className="text-body font-medium">
            {label}
          </label>
        ) : (
          <span className="text-body font-medium">{label}</span>
        )}
        {aside !== undefined && aside !== null && aside !== false && (
          <span className="text-caption text-muted-foreground tabular-nums">
            {aside}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

export { INPUT } from "@/components/ui/native-select";
