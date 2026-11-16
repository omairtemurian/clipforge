import { ArrowsHorizontalIcon } from "@phosphor-icons/react";
import type { Word } from "@/api/types";
import type { Handle } from "@/lib/timeline";
import { inRuns, type WordRun } from "@/lib/transcriptView";
import { cn } from "@/lib/utils";

export interface IndexedWord {
  word: Word;
  index: number;
}

interface ContextWordProps {
  item: IndexedWord;
  handle: Handle;
  offered: boolean;
  matched: boolean;
  onOffer: (index: number | null) => void;
  onExtend: (handle: Handle, t: number) => void;
}

/** A word outside the clip: grayed; a click offers "Extend to here". */
function ContextWord({
  item,
  handle,
  offered,
  matched,
  onOffer,
  onExtend,
}: ContextWordProps) {
  const { word, index } = item;
  const extend = offered && (
    <button
      type="button"
      onClick={() => {
        onExtend(handle, handle === "start" ? word.start : word.end);
        onOffer(null);
      }}
      className="mx-1 inline-flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 align-middle text-caption leading-5 font-medium text-primary-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <ArrowsHorizontalIcon className="size-3" aria-hidden />
      Extend to here
    </button>
  );
  return (
    <>
      {handle === "start" && extend}
      <span
        data-word={index}
        title="Click to extend the clip to here"
        onClick={() => onOffer(offered ? null : index)}
        className={cn(
          "cursor-pointer rounded px-0.5 transition-colors hover:text-foreground",
          matched && "bg-highlight/20",
          offered && "text-foreground underline decoration-primary",
        )}
      >
        {word.text}
      </span>
      {handle === "end" && extend}{" "}
    </>
  );
}

interface TranscriptContextProps {
  words: IndexedWord[];
  handle: Handle;
  label: string;
  offered: number | null;
  matches: WordRun[];
  onOffer: (index: number | null) => void;
  onExtend: (handle: Handle, t: number) => void;
}

/** The grayed words before (handle "start") or after ("end") the clip that
 * "Extend a clip" shows; nothing if there are none. */
export function TranscriptContext({
  words,
  handle,
  label,
  offered,
  matches,
  onOffer,
  onExtend,
}: TranscriptContextProps) {
  if (words.length === 0) return null;
  return (
    <section aria-label={label} className="text-muted-foreground/70">
      <h3 className="mb-1 text-micro font-medium text-muted-foreground">
        {label}
      </h3>
      <p>
        {words.map((item) => (
          <ContextWord
            key={item.index}
            item={item}
            handle={handle}
            offered={offered === item.index}
            matched={inRuns(matches, item.index)}
            onOffer={onOffer}
            onExtend={onExtend}
          />
        ))}
      </p>
    </section>
  );
}
