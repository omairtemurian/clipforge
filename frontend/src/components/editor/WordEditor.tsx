import {
  ArrowCounterClockwiseIcon,
  PaletteIcon,
  SlidersHorizontalIcon,
} from "@phosphor-icons/react";
import { Popover } from "radix-ui";
import { useState } from "react";
import type { CaptionMark, Word } from "@/api/types";
import { ColorField } from "@/components/editor/ColorField";
import { ChoiceChips } from "@/components/settings/ChoiceChips";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { formatTimecode } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  EMOJI_CHOICES,
  isEmoji,
  markFields,
  markOf,
  withMark,
  withoutUserMark,
  type MarkFields,
} from "@/lib/wordMarks";

type Tri = "auto" | "on" | "off";

function tri(value: boolean | null): Tri {
  return value === null ? "auto" : value ? "on" : "off";
}

function fromTri(value: Tri): boolean | null {
  return value === "auto" ? null : value === "on";
}

const HIGHLIGHT = [
  { value: "auto", label: "Auto" },
  { value: "on", label: "Highlight" },
  { value: "off", label: "Plain" },
] as const satisfies { value: Tri; label: string }[];

const CENSOR = [
  { value: "auto", label: "Auto" },
  { value: "on", label: "Censor" },
  { value: "off", label: "Never" },
] as const satisfies { value: Tri; label: string }[];

const EMOJI_CHIP =
  "inline-flex h-8 min-w-8 items-center justify-center rounded-full border px-2 text-body transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

interface WordEditorProps {
  word: Word;
  /** The clip's word marks (caption_style.word_marks). */
  marks: CaptionMark[] | null;
  /** dragged: the change is one of a color picker's drag. */
  onChange: (marks: CaptionMark[], dragged?: boolean) => void;
  /** Called when the color picker is first used. */
  onStart?: () => void;
  /** The color the word shows without a color of its own. */
  baseColor: string;
}

/** The button of a caption word's popover: the word's emoji or color when
 * its mark sets one. */
function Trigger({ fields }: { fields: MarkFields }) {
  if (fields.emoji) return <span aria-hidden>{fields.emoji}</span>;
  if (fields.color) {
    return (
      <span
        aria-hidden
        className="size-3.5 rounded-full border border-border"
        style={{ background: fields.color }}
      />
    );
  }
  return fields.emphasis || fields.censor ? (
    <PaletteIcon className="text-primary-ink" aria-hidden />
  ) : (
    <SlidersHorizontalIcon aria-hidden />
  );
}

/**
 * The per-word edit popover of a caption word: highlight it as an emphasis
 * word (or keep it plain), put an emoji after it, censor it (or never) and
 * give it a color of its own. "Auto" leaves each to the clip (its emphasis
 * words, emoji map and censor lists) or to the AI's mark of the word.
 */
export function WordEditor({
  word,
  marks,
  onChange,
  onStart,
  baseColor,
}: WordEditorProps) {
  const fields = markFields(marks, word);
  const [typed, setTyped] = useState("");
  const set = (change: Partial<MarkFields>, dragged = false) =>
    onChange(withMark(marks, word, change), dragged);
  const own = markOf(marks, word)?.source === "user";
  const time = formatTimecode(word.start);
  const marked = Object.values(fields).some((value) => value !== null);

  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={`Edit word at ${time}`}
        className={cn(
          "inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md border text-micro transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-3.5",
          marked
            ? "border-primary/60 text-foreground"
            : "border-border text-muted-foreground",
        )}
      >
        <Trigger fields={fields} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="left"
          align="start"
          sideOffset={8}
          aria-label={`Word "${word.text.trim()}"`}
          className="z-[60] flex w-72 flex-col gap-4 rounded-xl border border-border bg-popover p-4 text-popover-foreground shadow-popover outline-none"
        >
          <p className="text-body font-medium">
            “{word.text.trim()}”{" "}
            <span className="text-caption text-muted-foreground tabular-nums">
              {time}
            </span>
          </p>
          <Field label="Highlight">
            <ChoiceChips
              label="Highlight"
              options={[...HIGHLIGHT]}
              value={tri(fields.emphasis)}
              onChange={(value) => set({ emphasis: fromTri(value) })}
            />
          </Field>
          <Field label="Emoji">
            <div
              role="group"
              aria-label="Emoji"
              className="flex flex-wrap gap-1.5"
            >
              {(
                [
                  [null, "Auto"],
                  ["", "None"],
                  ...EMOJI_CHOICES.map((emoji) => [emoji, emoji]),
                ] as [string | null, string][]
              ).map(([value, label]) => (
                <button
                  key={label}
                  type="button"
                  aria-pressed={fields.emoji === value}
                  onClick={() => set({ emoji: value })}
                  className={cn(
                    EMOJI_CHIP,
                    fields.emoji === value
                      ? "border-primary bg-primary/15 text-primary-ink"
                      : "border-border text-muted-foreground hover:bg-muted",
                  )}
                >
                  {label}
                </button>
              ))}
              <input
                aria-label="Other emoji"
                placeholder="Other"
                value={typed}
                onChange={(event) => {
                  const text = event.target.value.trim();
                  setTyped(text);
                  if (isEmoji(text)) set({ emoji: text });
                }}
                className={cn(INPUT, "h-8 w-20 px-2")}
              />
            </div>
          </Field>
          <Field label="Censor">
            <ChoiceChips
              label="Censor"
              options={[...CENSOR]}
              value={tri(fields.censor)}
              onChange={(value) => set({ censor: fromTri(value) })}
            />
          </Field>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <ColorField
                label="Word color"
                value={fields.color ?? baseColor}
                onChange={(color) => set({ color }, true)}
                onStart={onStart}
              />
            </div>
            {fields.color && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mb-6"
                onClick={() => set({ color: null })}
              >
                Auto color
              </Button>
            )}
          </div>
          {own && (
            <Button
              type="button"
              variant="outline"
              onClick={() => onChange(withoutUserMark(marks, word))}
            >
              <ArrowCounterClockwiseIcon aria-hidden />
              Reset the word
            </Button>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
