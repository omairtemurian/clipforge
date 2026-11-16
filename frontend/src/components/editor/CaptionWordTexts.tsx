import type { CaptionMark, Word } from "@/api/types";
import { WordEditor } from "@/components/editor/WordEditor";
import { INPUT } from "@/components/settings/Field";
import { formatTimecode } from "@/lib/format";
import { cn } from "@/lib/utils";
import { captionText, withWordText } from "@/lib/wordTexts";

interface CaptionWordTextsProps {
  /** The words the captions show. */
  words: Word[];
  overrides: Word[];
  onChange: (overrides: Word[]) => void;
  /** The clip's word marks, edited in each word's popover (WordEditor). */
  marks: CaptionMark[] | null;
  onMarks: (marks: CaptionMark[], dragged?: boolean) => void;
  onMarkStart?: () => void;
  /** The color of a word without a color of its own. */
  baseColor: string;
}

/** One text field for each caption word of the clip, in order, with the
 * word's time; a changed text is kept as an override, a blank one hides the
 * word. The button after it opens the word's popover (highlight, emoji,
 * censor, color). */
export function CaptionWordTexts({
  words,
  overrides,
  onChange,
  marks,
  onMarks,
  onMarkStart,
  baseColor,
}: CaptionWordTextsProps) {
  if (words.length === 0) {
    return (
      <p className="text-body text-muted-foreground">
        The clip has no words to caption.
      </p>
    );
  }
  return (
    <ul aria-label="Caption words" className="flex flex-col gap-1">
      {words.map((word) => {
        const text = captionText(word, overrides);
        const edited = text !== word.text.trim();
        return (
          <li
            key={`${word.start}-${word.end}`}
            className="flex items-center gap-2"
          >
            <span className="w-14 shrink-0 text-micro text-muted-foreground tabular-nums">
              {formatTimecode(word.start)}
            </span>
            <input
              aria-label={`Caption text at ${formatTimecode(word.start)}`}
              value={text}
              onChange={(event) =>
                onChange(withWordText(overrides, word, event.target.value))
              }
              className={cn(
                INPUT,
                "h-7 px-2",
                edited && "border-primary text-primary-ink",
              )}
            />
            <WordEditor
              word={word}
              marks={marks}
              onChange={onMarks}
              onStart={onMarkStart}
              baseColor={baseColor}
            />
          </li>
        );
      })}
    </ul>
  );
}
