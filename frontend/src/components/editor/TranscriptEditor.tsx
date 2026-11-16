import { PlusIcon } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import type { Word } from "@/api/types";
import { ClipWords } from "@/components/editor/ClipWords";
import type { CaptionTarget } from "@/components/editor/SelectionToolbar";
import { SpeechCleanup } from "@/components/editor/SpeechCleanup";
import {
  TranscriptContext,
  type IndexedWord,
} from "@/components/editor/TranscriptContext";
import { TranscriptToolbar } from "@/components/editor/TranscriptToolbar";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { useTranscriptSearch } from "@/hooks/useTranscriptSearch";
import {
  isCut,
  selectionBounds,
  wordPlace,
  type WordSelection,
} from "@/lib/cuts";
import type { ClipRange } from "@/lib/timeline";
import { toast } from "@/lib/toast";
import {
  CLIP_TEXT_LIMITS,
  fitText,
  transcriptText,
  wordAt,
} from "@/lib/transcriptView";
import { cn } from "@/lib/utils";

interface TranscriptEditorProps {
  clipId: number;
  projectId: number;
  /** The words of the clip and its context, in source order. */
  words: Word[];
  edits: ClipEdits;
  /** How far "extend to here" may move the clip (the context shown). */
  bounds: ClipRange;
  selection: WordSelection | null;
  onSelect: (selection: WordSelection | null) => void;
  onSeek: (t: number) => void;
  /** Cut the selected words. */
  onDelete: () => void;
  /** The source time being played and whether the preview plays. */
  playhead: number;
  playing: boolean;
}

const CAPTION_NAMES: Record<CaptionTarget, string> = {
  hook_text: "Hook",
  title: "Title",
};

/**
 * The editor's transcript: the clip's words with its pauses as pills. A
 * click on a word plays from it and selects it; dragging (or shift+click)
 * selects a run of words, under which a toolbar uses them as the hook or
 * title or cuts them. Cut words are struck through and a click brings them
 * back. "Extend a clip" shows 30 s of grayed context, whose words offer to
 * extend the clip to them; "Speech cleanup" reviews filler and pause cuts.
 * The word being played is marked and a search marks the words it finds.
 */
export function TranscriptEditor({
  clipId,
  projectId,
  words,
  edits,
  bounds,
  selection,
  onSelect,
  onSeek,
  onDelete,
  playhead,
  playing,
}: TranscriptEditorProps) {
  const { range, cuts } = edits;
  const [dragging, setDragging] = useState(false);
  const [offered, setOffered] = useState<number | null>(null);
  const [extending, setExtending] = useState(false);
  const [cleanup, setCleanup] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  const items = words.map((word, index) => ({ word, index }));
  const part = (place: ReturnType<typeof wordPlace>) =>
    items.filter(({ word }) => wordPlace(word, range) === place);
  const [before, inside, after] = [
    part("before"),
    part("inside"),
    part("after"),
  ];
  const search = useTranscriptSearch(
    words,
    (index) => extending || wordPlace(words[index], range) === "inside",
  );
  const current = playing ? wordAt(words, playhead) : -1;
  const target = search.activeMatch?.[0] ?? (playing ? current : -1);

  useEffect(() => {
    const stop = () => setDragging(false);
    window.addEventListener("pointerup", stop);
    return () => window.removeEventListener("pointerup", stop);
  }, []);

  useEffect(() => {
    if (target < 0) return;
    const element = container.current?.querySelector(`[data-word="${target}"]`);
    element?.scrollIntoView?.({ block: "nearest" });
  }, [target]);

  const press = (event: PointerEvent, { word, index }: IndexedWord) => {
    if (event.button !== 0) return;
    event.preventDefault();
    setOffered(null);
    if (event.shiftKey && selection) {
      onSelect({ anchor: selection.anchor, focus: index });
      return;
    }
    setDragging(true);
    onSelect({ anchor: index, focus: index });
    onSeek(word.start);
  };
  const enter = (index: number) => {
    if (dragging && selection) {
      onSelect({ anchor: selection.anchor, focus: index });
    }
  };
  const caption = (field: CaptionTarget) => {
    if (!selection) return;
    const [first, last] = selectionBounds(selection);
    const chosen = words.slice(first, last + 1).filter((w) => !isCut(w, cuts));
    const text = fitText(transcriptText(chosen), CLIP_TEXT_LIMITS[field]);
    if (!text) return;
    edits.setTexts({ [field]: text });
    toast.success(`${CAPTION_NAMES[field]} set to “${text}”.`);
    onSelect(null);
  };
  const extend = (handle: "start" | "end", t: number) =>
    edits.extend(handle, t, bounds);
  const context = (
    list: IndexedWord[],
    handle: "start" | "end",
    label: string,
  ) =>
    extending && (
      <TranscriptContext
        words={list}
        handle={handle}
        label={label}
        offered={offered}
        matches={search.matches}
        onOffer={setOffered}
        onExtend={extend}
      />
    );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <TranscriptToolbar
        search={search.state}
        onCleanup={() => setCleanup(true)}
        onSearchOpen={search.setOpen}
        onQuery={search.setQuery}
        onStep={search.step}
        clipId={clipId}
        projectId={projectId}
      />
      <div className="shrink-0">
        <button
          type="button"
          aria-pressed={extending}
          onClick={() => {
            setExtending(!extending);
            setOffered(null);
          }}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-body transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50",
            extending && "border-primary/60 bg-primary/10 text-foreground",
          )}
        >
          <PlusIcon className="size-4" aria-hidden />
          Extend a clip
        </button>
        {extending && (
          <p className="mt-2 text-caption text-muted-foreground">
            Click a gray word to extend the clip to it.
          </p>
        )}
      </div>
      <div
        ref={container}
        data-transcript
        aria-label="Transcript"
        className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto rounded-xl [&>*]:shrink-0 border border-border bg-muted/20 p-4 text-[15px] leading-8 select-none"
      >
        {context(before, "start", "Before the clip")}
        <ClipWords
          words={words}
          inside={inside}
          range={range}
          cuts={cuts}
          selection={selection}
          dragging={dragging}
          current={current}
          matches={search.matches}
          activeMatch={search.activeMatch}
          onPress={press}
          onEnter={enter}
          onRestore={edits.restore}
          onCaption={caption}
          onDelete={onDelete}
        />
        {context(after, "end", "After the clip")}
      </div>
      <SpeechCleanup
        clipId={clipId}
        range={range}
        cuts={cuts}
        open={cleanup}
        onOpenChange={setCleanup}
        onApply={edits.cutAll}
      />
    </div>
  );
}
