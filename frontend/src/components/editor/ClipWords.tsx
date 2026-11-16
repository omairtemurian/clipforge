import type { PointerEvent } from "react";
import type { Word } from "@/api/types";
import {
  SelectionToolbar,
  type CaptionTarget,
} from "@/components/editor/SelectionToolbar";
import type { IndexedWord } from "@/components/editor/TranscriptContext";
import {
  cutAt,
  isCut,
  isSelected,
  selectionBounds,
  wordMiddle,
  type WordSelection,
} from "@/lib/cuts";
import type { ClipRange, CutRange } from "@/lib/timeline";
import {
  formatPause,
  inRuns,
  pausesBefore,
  type WordRun,
} from "@/lib/transcriptView";
import { cn } from "@/lib/utils";

interface ClipWordsProps {
  /** All words of the transcript (for the pauses), and the clip's. */
  words: Word[];
  inside: IndexedWord[];
  range: ClipRange;
  cuts: CutRange[];
  selection: WordSelection | null;
  /** Whether the selection is being dragged (no toolbar meanwhile). */
  dragging: boolean;
  /** The index of the word being played, -1 if none. */
  current: number;
  matches: WordRun[];
  activeMatch: WordRun | null;
  onPress: (event: PointerEvent, item: IndexedWord) => void;
  onEnter: (index: number) => void;
  onRestore: (t: number) => void;
  onCaption: (target: CaptionTarget) => void;
  onDelete: () => void;
}

/** A pause before a word as a small gray pill with its length; struck
 * through when a cut removes it. */
function PausePill({ seconds, cut }: { seconds: number; cut: boolean }) {
  const label = formatPause(seconds);
  return (
    <>
      <span
        aria-label={`Pause ${label}${cut ? " (cut)" : ""}`}
        data-cut={cut || undefined}
        className={cn(
          "mx-0.5 inline-block rounded bg-muted px-1.5 align-middle text-micro leading-5 text-muted-foreground tabular-nums",
          cut && "bg-primary/10 line-through decoration-primary",
        )}
      >
        {label}
      </span>{" "}
    </>
  );
}

/**
 * The words of the clip as running text: pauses as pills, cut words struck
 * through (a click restores them), the selection highlighted with its
 * toolbar, the word being played and the search's matches marked.
 */
export function ClipWords({
  words,
  inside,
  range,
  cuts,
  selection,
  dragging,
  current,
  matches,
  activeMatch,
  onPress,
  onEnter,
  onRestore,
  onCaption,
  onDelete,
}: ClipWordsProps) {
  const pauses = pausesBefore(words, range);
  const first = selection && selectionBounds(selection)[0];

  return (
    <p aria-label="Clip words">
      {inside.length === 0 && (
        <span className="text-body text-muted-foreground">
          No words are spoken in this clip.
        </span>
      )}
      {inside.map((item) => {
        const { word, index } = item;
        const cut = isCut(word, cuts);
        const selected = isSelected(selection, index);
        const pause = pauses.get(index);
        const active =
          activeMatch !== null &&
          index >= activeMatch[0] &&
          index <= activeMatch[1];
        return (
          <span key={index}>
            {pause !== undefined && (
              <PausePill
                seconds={pause}
                cut={cutAt(cuts, word.start - pause / 2) !== undefined}
              />
            )}
            {!dragging && first === index && (
              <SelectionToolbar onCaption={onCaption} onDelete={onDelete} />
            )}
            <span
              data-word={index}
              data-cut={cut || undefined}
              data-selected={selected || undefined}
              data-current={index === current || undefined}
              data-match={inRuns(matches, index) || undefined}
              title={cut ? "Cut. Click to restore" : undefined}
              onPointerDown={(event) =>
                cut ? event.preventDefault() : onPress(event, item)
              }
              onPointerEnter={() => onEnter(index)}
              onClick={() => cut && onRestore(wordMiddle(word))}
              className={cn(
                "cursor-pointer rounded px-0.5 py-1 transition-colors hover:bg-muted",
                inRuns(matches, index) && "bg-highlight/20",
                active && "bg-highlight/40 ring-1 ring-highlight/70",
                index === current &&
                  "text-primary-ink underline decoration-primary/60 underline-offset-4",
                selected && "bg-primary/30 hover:bg-primary/40",
                cut &&
                  "bg-primary/10 text-muted-foreground line-through decoration-primary decoration-2",
              )}
            >
              {word.text}
            </span>{" "}
          </span>
        );
      })}
    </p>
  );
}
