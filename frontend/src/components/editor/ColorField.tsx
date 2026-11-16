interface ColorFieldProps {
  label: string;
  value: string;
  disabled?: boolean;
  onChange: (color: string) => void;
  /** Called when the color picker is first used. */
  onStart?: () => void;
}

/** A color swatch with its name and hex value; clicking it opens the
 * browser's color picker. */
export function ColorField({
  label,
  value,
  disabled,
  onChange,
  onStart,
}: ColorFieldProps) {
  return (
    <label className="flex flex-col items-start gap-1.5 text-caption text-muted-foreground">
      {label}
      <input
        type="color"
        aria-label={label}
        value={value.toLowerCase()}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onFocus={onStart}
        onPointerDown={onStart}
        className="h-8 w-full cursor-pointer rounded-lg border border-border bg-transparent p-0.5 disabled:opacity-50"
      />
      <span className="font-mono tabular-nums">{value.toUpperCase()}</span>
    </label>
  );
}
