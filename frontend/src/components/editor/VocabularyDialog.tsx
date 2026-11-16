import { useState } from "react";
import { useSaveVocabulary, useVocabulary } from "@/api/captions";
import type { Vocabulary } from "@/api/types";
import { ReplaceEverywhere } from "@/components/editor/ReplaceEverywhere";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";
import { correctionsText, linesOf, parseCorrections } from "@/lib/captionLists";
import { cn } from "@/lib/utils";

const AREA = cn(INPUT, "py-2");

function VocabularyForm({ saved }: { saved: Vocabulary }) {
  const [terms, setTerms] = useState(saved.terms.join("\n"));
  const [corrections, setCorrections] = useState(
    correctionsText(saved.corrections),
  );
  const save = useSaveVocabulary();
  const parsed = parseCorrections(corrections);

  return (
    <form
      aria-label="Brand vocabulary"
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate({
          terms: linesOf(terms),
          corrections: parsed.corrections,
        });
      }}
    >
      <Field label="Terms" htmlFor="vocabulary-terms">
        <textarea
          id="vocabulary-terms"
          rows={4}
          value={terms}
          onChange={(event) => setTerms(event.target.value)}
          placeholder={"ClipForge\nKubernetes"}
          className={AREA}
        />
      </Field>
      <Field label="Corrections" htmlFor="vocabulary-corrections">
        <textarea
          id="vocabulary-corrections"
          rows={4}
          value={corrections}
          onChange={(event) => setCorrections(event.target.value)}
          placeholder="clip forge = ClipForge"
          className={cn(AREA, "font-mono")}
        />
      </Field>
      {parsed.bad.length > 0 && (
        <p role="alert" className="text-caption text-destructive">
          Write each correction as “heard = correct” (line{" "}
          {parsed.bad.join(", ")}).
        </p>
      )}
      <div className="flex justify-end">
        <Button
          type="submit"
          disabled={parsed.bad.length > 0 || save.isPending}
        >
          Save vocabulary
        </Button>
      </div>
    </form>
  );
}

interface VocabularyDialogProps {
  projectId: number;
  /** Why replace everywhere cannot run now, or null. */
  replaceBlocked: string | null;
  onReplaced: () => void;
  onClose: () => void;
}

/**
 * The brand vocabulary: terms that transcription listens for (Whisper's
 * hotwords) and corrections applied to every new transcript, one per
 * line; and "Replace everywhere" in this project.
 */
export function VocabularyDialog({
  projectId,
  replaceBlocked,
  onReplaced,
  onClose,
}: VocabularyDialogProps) {
  const vocabulary = useVocabulary();
  return (
    <DialogFrame
      wide
      title="Brand vocabulary"
      description="Terms are listened for when a video is transcribed; corrections fix every new transcript (whole words, any case)."
      onClose={onClose}
    >
      <div className="mt-4 flex flex-col gap-6">
        {vocabulary.data ? (
          <VocabularyForm saved={vocabulary.data} />
        ) : (
          <p className="text-body text-muted-foreground">
            {vocabulary.isError
              ? "Could not load the vocabulary."
              : "Loading the vocabulary."}
          </p>
        )}
        <section className="flex flex-col gap-3 border-t border-border pt-4">
          <h3 className="text-section">Replace everywhere in this project</h3>
          <ReplaceEverywhere
            projectId={projectId}
            blocked={replaceBlocked}
            onReplaced={onReplaced}
          />
        </section>
      </div>
    </DialogFrame>
  );
}
