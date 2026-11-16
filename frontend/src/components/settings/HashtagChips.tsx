import { XIcon } from "@phosphor-icons/react";
import { useId, useState } from "react";
import { Field, INPUT } from "@/components/settings/Field";
import { addHashtags } from "@/lib/clipText";
import { cn } from "@/lib/utils";

interface HashtagChipsProps {
  label: string;
  /** The hashtags without "#". */
  value: string[];
  onChange: (tags: string[]) => void;
  hint?: string;
  /** The most hashtags that can be added. */
  max?: number;
  disabled?: boolean;
}

/** A labelled list of hashtag chips with a box to add more: Enter, comma or
 * space (or leaving the box) adds what was typed or pasted; each chip has a
 * remove button, and Backspace in the empty box removes the last one. */
export function HashtagChips({
  label,
  value,
  onChange,
  hint,
  max = 30,
  disabled,
}: HashtagChipsProps) {
  const id = useId();
  const [typed, setTyped] = useState("");

  function commit(text: string) {
    const next = addHashtags(value, text, max);
    if (next.length !== value.length) onChange(next);
    setTyped("");
  }

  return (
    <Field label={label} htmlFor={id}>
      <div
        className={cn(
          INPUT,
          "flex min-h-9 flex-wrap items-center gap-1.5 py-1.5 focus-within:ring-3 focus-within:ring-ring/50",
        )}
      >
        {value.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-full border border-primary bg-primary/15 py-0.5 pr-1 pl-2.5 text-body text-primary-ink"
          >
            #{tag}
            <button
              type="button"
              aria-label={`Remove #${tag}`}
              disabled={disabled}
              onClick={() => onChange(value.filter((each) => each !== tag))}
              className="rounded-full p-0.5 outline-none hover:bg-primary/20 focus-visible:ring-2 focus-visible:ring-ring [&_svg]:size-3"
            >
              <XIcon aria-hidden />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={typed}
          disabled={disabled || value.length >= max}
          placeholder={value.length === 0 ? "Add a hashtag" : ""}
          aria-describedby={hint ? `${id}-hint` : undefined}
          spellCheck={false}
          onChange={(event) => {
            const text = event.target.value;
            if (/[\s,]$/.test(text)) commit(text);
            else setTyped(text);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit(typed);
            } else if (
              event.key === "Backspace" &&
              typed === "" &&
              value.length > 0
            ) {
              onChange(value.slice(0, -1));
            }
          }}
          onBlur={() => commit(typed)}
          className="h-6 min-w-28 flex-1 bg-transparent text-body outline-none"
        />
      </div>
      {hint && (
        <p id={`${id}-hint`} className="text-caption text-muted-foreground">
          {hint}
        </p>
      )}
    </Field>
  );
}
