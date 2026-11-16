import { CircleNotchIcon, SparkleIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useRegenerateText } from "@/api/clipActions";
import type { Clip } from "@/api/types";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import type { ClipEdits } from "@/hooks/useClipEdits";
import {
  DESCRIPTION_MAX,
  HASHTAGS_MAX,
  HASHTAGS_MIN,
  HOOK_MAX,
  TITLE_MAX,
  formatHashtags,
  parseHashtags,
  textProblems,
} from "@/lib/clipText";
import { cn } from "@/lib/utils";

function sameTags(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((tag, index) => tag === b[index]);
}

function Problem({ id, text }: { id: string; text: string | undefined }) {
  return (
    text && (
      <p id={id} role="alert" className="text-caption text-destructive">
        {text}
      </p>
    )
  );
}

/**
 * The editor's Text tab: the clip's title, hook text (burned into the
 * video's first seconds), description and hashtags, with their character
 * limits, and "Regenerate with AI", which writes the title, description and
 * hashtags again from what the clip says.
 */
export function TextPanel({ clip, edits }: { clip: Clip; edits: ClipEdits }) {
  const { title, hook_text: hook, description, hashtags } = edits.texts;
  const regenerate = useRegenerateText(clip.id);
  const problems = textProblems(edits.texts);
  // The hashtag input keeps what is typed ("#pizza, #fu"); undo shows the list.
  const [draft, setDraft] = useState(formatHashtags(hashtags));
  const typed = sameTags(parseHashtags(draft), hashtags)
    ? draft
    : formatHashtags(hashtags);

  const regenerated = async () => {
    try {
      const next = await regenerate.mutateAsync();
      edits.setTexts({
        title: next.title,
        description: next.description,
        hashtags: next.hashtags,
      });
      setDraft(formatHashtags(next.hashtags));
    } catch {
      // apiFetch has shown the error
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <Field
        label="Title"
        htmlFor="text-title"
        aside={`${title.length}/${TITLE_MAX}`}
      >
        <input
          id="text-title"
          value={title}
          maxLength={TITLE_MAX}
          aria-invalid={problems.title !== undefined}
          onChange={(event) => edits.setTexts({ title: event.target.value })}
          className={cn(INPUT, "h-9")}
        />
      </Field>
      <Field
        label="Hook text"
        htmlFor="text-hook"
        aside={`${hook.length}/${HOOK_MAX}`}
      >
        <input
          id="text-hook"
          value={hook}
          maxLength={HOOK_MAX}
          aria-invalid={problems.hook_text !== undefined}
          onChange={(event) =>
            edits.setTexts({ hook_text: event.target.value })
          }
          className={cn(INPUT, "h-9")}
        />
      </Field>
      <Field
        label="Description"
        htmlFor="text-description"
        aside={`${description.length}/${DESCRIPTION_MAX}`}
      >
        <textarea
          id="text-description"
          rows={5}
          value={description}
          maxLength={DESCRIPTION_MAX}
          aria-invalid={problems.description !== undefined}
          onChange={(event) =>
            edits.setTexts({ description: event.target.value })
          }
          className={cn(INPUT, "resize-none py-2")}
        />
      </Field>
      <Field
        label="Hashtags"
        htmlFor="text-hashtags"
        aside={`${hashtags.length} (${HASHTAGS_MIN}-${HASHTAGS_MAX})`}
      >
        <textarea
          id="text-hashtags"
          rows={2}
          value={typed}
          placeholder="#funny #standup #pizza"
          aria-invalid={problems.hashtags !== undefined}
          aria-describedby="text-hashtags-problem"
          onChange={(event) => {
            setDraft(event.target.value);
            edits.setTexts({ hashtags: parseHashtags(event.target.value) });
          }}
          className={cn(INPUT, "resize-none py-2")}
        />
        <Problem id="text-hashtags-problem" text={problems.hashtags} />
      </Field>
      <Button
        variant="outline"
        disabled={regenerate.isPending}
        onClick={() => void regenerated()}
      >
        {regenerate.isPending ? (
          <CircleNotchIcon className="animate-spin" aria-hidden />
        ) : (
          <SparkleIcon aria-hidden />
        )}
        Regenerate with AI
      </Button>
      <p className="-mt-2 text-caption text-muted-foreground">
        Writes a new title, description and hashtags from what the clip says and
        saves them. The hook text stays.
      </p>
    </div>
  );
}
