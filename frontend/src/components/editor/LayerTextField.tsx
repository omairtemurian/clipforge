import { useState } from "react";
import type { TrackItem } from "@/api/types";
import { Field, INPUT } from "@/components/settings/Field";
import { TEXT_MAX, textProps } from "@/lib/overlays";
import { cn } from "@/lib/utils";

interface LayerTextFieldProps {
  item: TrackItem;
  onText: (text: string) => void;
}

/** A text layer's text; emptying it keeps the last text until more is
 * typed (a text layer needs text). */
export function LayerTextField({ item, onText }: LayerTextFieldProps) {
  const text = textProps(item).text;
  const [empty, setEmpty] = useState(false);
  return (
    <Field
      label="Text"
      htmlFor="text-layer-text"
      aside={`${empty ? 0 : text.length}/${TEXT_MAX}`}
    >
      <textarea
        id="text-layer-text"
        rows={2}
        value={empty ? "" : text}
        maxLength={TEXT_MAX}
        aria-invalid={empty}
        onChange={(event) => {
          const next = event.target.value;
          setEmpty(next.trim() === "");
          if (next.trim() !== "") onText(next);
        }}
        className={cn(INPUT, "resize-none py-2")}
      />
      {empty && (
        <p role="alert" className="text-caption text-destructive">
          A text layer needs text.
        </p>
      )}
    </Field>
  );
}
