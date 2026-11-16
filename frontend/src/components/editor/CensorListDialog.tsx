import { useState } from "react";
import { useCensorWords, useSaveCensorWords } from "@/api/captions";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";
import { linesOf } from "@/lib/captionLists";
import { cn } from "@/lib/utils";

function CensorListForm({
  words,
  onClose,
}: {
  words: string[];
  onClose: () => void;
}) {
  const [text, setText] = useState(words.join("\n"));
  const save = useSaveCensorWords(onClose);
  return (
    <form
      className="mt-4 flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate({ words: linesOf(text) });
      }}
    >
      <textarea
        aria-label="Censored words"
        rows={8}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={"darn\nheck*"}
        className={cn(INPUT, "py-2 font-mono")}
      />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          Save list
        </Button>
      </div>
    </form>
  );
}

/** The custom censor list: one word per line (a trailing * censors every
 * word that starts with it), censored with the default list. */
export function CensorListDialog({ onClose }: { onClose: () => void }) {
  const words = useCensorWords();
  return (
    <DialogFrame
      title="Censor list"
      description="One word per line, any case. End a word with * to censor every word that starts with it. These words are censored with the built-in list."
      onClose={onClose}
    >
      {words.data ? (
        <CensorListForm words={words.data.words} onClose={onClose} />
      ) : (
        <p className="mt-4 text-body text-muted-foreground">
          {words.isError ? "Could not load the list." : "Loading the list."}
        </p>
      )}
    </DialogFrame>
  );
}
