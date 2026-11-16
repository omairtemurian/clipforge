import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Choice<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

interface ChoiceChipsProps<T extends string> {
  /** Accessible name of the group. */
  label: string;
  options: Choice<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
}

const CHIP =
  "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-body transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-4";
const CHOSEN = "border-primary bg-primary/15 text-primary-ink";
const UNCHOSEN =
  "border-border text-muted-foreground hover:bg-muted hover:text-foreground";

/** A row of rounded chips of which one is chosen (a radio group). */
export function ChoiceChips<T extends string>({
  label,
  options,
  value,
  onChange,
  disabled,
}: ChoiceChipsProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const chosen = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={chosen}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              CHIP,
              chosen ? CHOSEN : UNCHOSEN,
              "disabled:pointer-events-none disabled:opacity-50",
            )}
          >
            {option.icon}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

interface MultiChoiceChipsProps<T extends string> {
  /** Accessible name of the group. */
  label: string;
  options: Choice<T>[];
  value: readonly T[];
  /** Called with the chip clicked; the caller works out the new choice. */
  onToggle: (value: T) => void;
}

/** A row of rounded chips of which any number are chosen (toggle buttons). */
export function MultiChoiceChips<T extends string>({
  label,
  options,
  value,
  onToggle,
}: MultiChoiceChipsProps<T>) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const chosen = value.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={chosen}
            onClick={() => onToggle(option.value)}
            className={cn(CHIP, chosen ? CHOSEN : UNCHOSEN)}
          >
            {option.icon}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
