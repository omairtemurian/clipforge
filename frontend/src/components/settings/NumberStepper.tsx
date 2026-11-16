import { useState } from "react";
import { MinusIcon, PlusIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";

interface NumberStepperProps {
  id: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}

/**
 * A whole number between min and max with - and + buttons. Typed text is
 * kept as typed until it leaves the field, then clamped into the range.
 */
export function NumberStepper({
  id,
  value,
  min,
  max,
  onChange,
}: NumberStepperProps) {
  const [text, setText] = useState<string | null>(null);
  const set = (next: number) =>
    onChange(Math.min(max, Math.max(min, Math.round(next))));

  function commit() {
    const typed = Number(text);
    if (text !== null && text.trim() !== "" && Number.isFinite(typed)) {
      set(typed);
    }
    setText(null);
  }

  return (
    <div className="flex w-fit items-center gap-1 rounded-full border border-border p-1">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="rounded-full"
        aria-label="Fewer clips"
        disabled={value <= min}
        onClick={() => set(value - 1)}
      >
        <MinusIcon aria-hidden />
      </Button>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={text ?? value}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
        }}
        className="w-10 [appearance:textfield] rounded-md bg-transparent text-center text-body font-medium tabular-nums outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&::-webkit-inner-spin-button]:appearance-none"
      />
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="rounded-full"
        aria-label="More clips"
        disabled={value >= max}
        onClick={() => set(value + 1)}
      >
        <PlusIcon aria-hidden />
      </Button>
    </div>
  );
}
