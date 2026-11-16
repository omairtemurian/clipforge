import { Switch } from "radix-ui";
import { cn } from "@/lib/utils";

interface ToggleRowProps {
  label: string;
  /** A line under the label that says what the switch does. */
  hint?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

/** A bordered row with a label, a hint and an on/off switch. */
export function ToggleRow({
  label,
  hint,
  checked,
  onCheckedChange,
  disabled,
  className,
}: ToggleRowProps) {
  return (
    <label
      className={cn(
        "flex items-center justify-between gap-4 rounded-xl border border-border bg-field px-3 py-2.5",
        className,
      )}
    >
      <span className="flex flex-col">
        <span className="text-body font-medium">{label}</span>
        {hint && (
          <span className="text-caption text-muted-foreground">{hint}</span>
        )}
      </span>
      <Switch.Root
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-label={label}
        className="relative h-5 w-9 shrink-0 rounded-full bg-input transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 data-[state=checked]:bg-primary"
      >
        <Switch.Thumb className="block size-4 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
      </Switch.Root>
    </label>
  );
}
